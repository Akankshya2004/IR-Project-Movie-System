"""
This file was written with the use of AI
Downloads and processes IMDb non-commercial datasets.

Downloads TSV files from IMDb (https://datasets.imdbws.com/), processes them,
and saves the extracted movie data into a JSON file.
"""

import requests
import gzip
import json
import pandas as pd
import os
from tqdm import tqdm

# --- Configuration ---
BASE_URL = "https://datasets.imdbws.com/"
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
RAW_DATA_DIR = os.path.join(DATA_DIR, 'raw', 'imdb_datasets')
OUTPUT_FILE = os.path.join(DATA_DIR, 'raw', 'imdb_movies.json')
CHUNK_SIZE = 100000
MOVIE_LIMIT = 250000 # Limit the number of movies to process
MIN_VOTES = 500 # Lowered from 5000 to include more movies
MIN_VOTES_RECENT = 50 # Threshold for very recent movies (2024-2025)

# File constants
TITLE_BASICS = "title.basics.tsv.gz"
TITLE_RATINGS = "title.ratings.tsv.gz"
TITLE_PRINCIPALS = "title.principals.tsv.gz"
NAME_BASICS = "name.basics.tsv.gz"

# Data types for efficient loading
DTYPES = {
    TITLE_BASICS: {'tconst': 'str', 'titleType': 'str', 'primaryTitle': 'str', 'startYear': 'str', 'genres': 'str'},
    TITLE_RATINGS: {'tconst': 'str', 'averageRating': 'float', 'numVotes': 'int'},
    TITLE_PRINCIPALS: {'tconst': 'str', 'ordering': 'int', 'nconst': 'str', 'category': 'str'},
    NAME_BASICS: {'nconst': 'str', 'primaryName': 'str'}
}

# Create directories if they don't exist
os.makedirs(RAW_DATA_DIR, exist_ok=True)

def download_file(filename):
    """Downloads a single file from the IMDb dataset URL if it doesn't exist."""
    url = BASE_URL + filename
    local_path = os.path.join(RAW_DATA_DIR, filename)
    
    if os.path.exists(local_path):
        print(f"File already exists: {filename}")
        return local_path

    print(f"Downloading {filename}...")
    try:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            with open(local_path, 'wb') as f, tqdm(
                total=total_size, unit='iB', unit_scale=True, desc=filename
            ) as pbar:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    pbar.update(len(chunk))
        print(f"Downloaded {filename} successfully.")
        return local_path
    except requests.exceptions.RequestException as e:
        print(f"Error downloading {filename}: {e}")
        return None

def load_tsv_in_chunks(filename, dtypes, filter_col=None, filter_set=None):
    """Loads and filters a gzipped TSV file in chunks to save memory."""
    path = os.path.join(RAW_DATA_DIR, filename)
    
    # Get total lines for progress bar
    print(f"Counting lines in {filename} for progress tracking...")
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        total_lines = sum(1 for _ in f)
    
    num_chunks = (total_lines // CHUNK_SIZE) + 1

    chunk_list = []
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        reader = pd.read_csv(
            f, sep='\\t', na_values=['\\N', 'nan'], quoting=3,
            dtype=dtypes, chunksize=CHUNK_SIZE, engine='python'
        )
        
        for chunk in tqdm(reader, total=num_chunks, desc=f"Loading {filename}"):
            if filter_col and filter_set:
                chunk = chunk[chunk[filter_col].isin(filter_set)]
            chunk_list.append(chunk)
    
    if not chunk_list:
        return pd.DataFrame()
    return pd.concat(chunk_list, ignore_index=True)

def process_data():
    """Processes the downloaded data and creates the final JSON output."""
    # Note: We regenerate the file to include new movies if criteria changed
    if os.path.exists(OUTPUT_FILE):
        print(f"IMDb data file found at {OUTPUT_FILE}.")
        print("Regenerating to ensure all movies (including new ones) are included...")
        
    print("\n--- Starting Data Processing ---")

    # Download all necessary files
    for filename in DTYPES.keys():
        if not download_file(filename):
            print("Failed to download a required file. Aborting.")
            return

    # 1. Load ratings and find popular movies
    print("\nStep 1: Finding popular movies from ratings...")
    ratings_df = load_tsv_in_chunks(TITLE_RATINGS, DTYPES[TITLE_RATINGS])
    
    # Load basics to get years for recent movie filtering
    print("   Loading basics for year filtering...")
    basics_df_years = load_tsv_in_chunks(TITLE_BASICS, {'tconst': 'str', 'startYear': 'str', 'titleType': 'str'})
    basics_df_years = basics_df_years[basics_df_years['titleType'] == 'movie']
    
    # Convert startYear to numeric, coercing errors to NaN
    basics_df_years['startYear'] = pd.to_numeric(basics_df_years['startYear'], errors='coerce')
    
    # Merge ratings with years
    merged_ratings = pd.merge(ratings_df, basics_df_years[['tconst', 'startYear']], on='tconst', how='inner')
    
    # Filter: High votes OR (Recent year AND Low votes)
    # Recent = 2024 or 2025
    mask_popular = merged_ratings['numVotes'] > MIN_VOTES
    mask_recent = (merged_ratings['startYear'] >= 2024) & (merged_ratings['numVotes'] > MIN_VOTES_RECENT)
    
    popular_movies_df = merged_ratings[mask_popular | mask_recent]
    
    popular_movies_df = popular_movies_df.sort_values(by='numVotes', ascending=False).head(MOVIE_LIMIT)
    popular_movie_ids = set(popular_movies_df['tconst'])
    print(f"Identified {len(popular_movie_ids)} popular/recent movies to process.")

    # 2. Load basics for popular movies only
    print("\nStep 2: Loading basic info for popular movies...")
    basics_df = load_tsv_in_chunks(TITLE_BASICS, DTYPES[TITLE_BASICS], 'tconst', popular_movie_ids)
    movies_df = basics_df[basics_df['titleType'] == 'movie'].copy()
    
    # 3. Merge ratings into the movie basics
    # Note: popular_movies_df has 'startYear' from the earlier merge, but basics_df also has it.
    # The merge might create startYear_x and startYear_y.
    # Let's drop startYear from popular_movies_df before merging to avoid confusion, 
    # as we want the one from basics_df (which is the source of truth for this step)
    if 'startYear' in popular_movies_df.columns:
        popular_movies_df = popular_movies_df.drop(columns=['startYear'])
        
    movies_df = pd.merge(movies_df, popular_movies_df, on='tconst', how='inner', validate="one_to_one")

    # 4. Load principals (cast/crew) for popular movies
    print("\nStep 3: Loading cast and crew for popular movies...")
    principals_df = load_tsv_in_chunks(TITLE_PRINCIPALS, DTYPES[TITLE_PRINCIPALS], 'tconst', popular_movie_ids)

    # 5. Load all names for lookup
    print("\nStep 4: Loading all names for lookups...")
    names_df = load_tsv_in_chunks(NAME_BASICS, DTYPES[NAME_BASICS])
    name_map = names_df.set_index('nconst')['primaryName'].to_dict()

    # 6. Process principals to get director and actor maps
    print("\nStep 5: Mapping directors and actors...")
    directors = principals_df[principals_df['category'] == 'director'].copy()
    directors['primaryName'] = directors['nconst'].map(name_map)
    director_map = directors.groupby('tconst')['primaryName'].apply(list).to_dict()

    actors = principals_df[principals_df['category'].isin(['actor', 'actress'])].copy()
    actors = actors.sort_values(by=['tconst', 'ordering'])
    top_actors = actors.groupby('tconst').head(5) # Top 5 actors
    top_actors['primaryName'] = top_actors['nconst'].map(name_map)
    actor_map = top_actors.groupby('tconst')['primaryName'].apply(list).to_dict()

    # 7. Assemble the final JSON data
    print("\nStep 6: Assembling final movie data...")
    movies_list = []
    for _, row in tqdm(movies_df.iterrows(), total=len(movies_df), desc="Creating JSON"):
        tconst = row['tconst']
        genres = row['genres'].split(',') if isinstance(row['genres'], str) else []
        
        movie_data = {
            'id': f"imdb_{tconst}",
            'tconst': tconst, # Keep for merging
            'title': row['primaryTitle'],
            'year': int(row['startYear']) if pd.notna(row['startYear']) and row['startYear'].isdigit() else None,
            'genres': [g for g in genres if g],
            'plot': None,
            'rating': row['averageRating'],
            'numVotes': int(row['numVotes']),
            'runtimeMinutes': None, # This info was removed from basics for performance
            'directors': director_map.get(tconst, []),
            'cast': actor_map.get(tconst, []),
            'source': 'imdb'
        }
        movies_list.append(movie_data)

    # 8. Save to JSON
    print(f"\nSaving {len(movies_list)} movies to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(movies_list, f, indent=2)
    print("IMDb data processing complete!")


if __name__ == "__main__":
    process_data()
