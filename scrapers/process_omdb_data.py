"""
Enriches movie data with information from the OMDb API.

Reads IMDb IDs from processed data and queries OMDb for additional details
like ratings from Rotten Tomatoes and Metacritic.

Requires an OMDb API key in a .env file.
"""

import requests
import json
import os
import time
from dotenv import load_dotenv
from typing import List, Dict, Optional
from tqdm import tqdm

# --- Configuration ---
API_BASE_URL = "https://www.omdbapi.com/"
IMDB_INPUT_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw', 'imdb_movies.json')
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw', 'omdb_movies.json')

# Load API credentials from .env file
load_dotenv()
API_KEY = os.getenv("OMDB_API_KEY")

class OMDbProcessor:
    """Enriches movie data using the OMDb API."""

    def __init__(self, input_file: str = IMDB_INPUT_FILE, output_file: str = OUTPUT_FILE):
        self.input_file = input_file
        self.output_file = output_file
        self.enriched_movies: List[Dict] = []

    def _get_imdb_ids(self) -> List[str]:
        """Loads IMDb IDs from the processed IMDb JSON file."""
        if not os.path.exists(self.input_file):
            print(f"ERROR: IMDb input file not found at {self.input_file}")
            print("Please run the process_imdb_data.py script first.")
            return []
        
        with open(self.input_file, 'r', encoding='utf-8') as f:
            imdb_data = json.load(f)
        
        ids = [movie.get('tconst') for movie in imdb_data if movie.get('tconst')]
        print(f"Loaded {len(ids)} IMDb IDs to process.")
        return ids

    def fetch_movie_data(self, imdb_id: str) -> Optional[Dict]:
        """Fetches data for a single movie from the OMDb API."""
        if not API_KEY:
            return None

        params = {
            "i": imdb_id,
            "apikey": API_KEY,
            "plot": "full"
        }
        try:
            response = requests.get(API_BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("Response") == "True":
                return data
            else:
                print(f"Warning: OMDb API returned an error for {imdb_id}: {data.get('Error')}")
                return None
        except requests.exceptions.RequestException as e:
            if e.response and e.response.status_code == 401:
                # This is a fatal error for the session, raise an exception to stop.
                raise ValueError("OMDb API key is invalid (401 Unauthorized). Halting OMDb processing.")
            print(f"Error fetching data for {imdb_id}: {e}")
            return None

    def process_movies(self, limit: int = 0):
        """
        Iterates through IMDb IDs, fetches data from OMDb, and saves it.
        """
        if not API_KEY:
            print("ERROR: OMDB_API_KEY not found.")
            print("Please create a .env file in the scrapers/ directory with your key.")
            return

        imdb_ids = self._get_imdb_ids()
        if not imdb_ids:
            return

        # Load existing OMDb data to avoid re-fetching
        existing_ids = set()
        if os.path.exists(self.output_file):
            with open(self.output_file, 'r', encoding='utf-8') as f:
                try:
                    existing_data = json.load(f)
                    self.enriched_movies = existing_data # Start with existing data
                    existing_ids = {m.get('imdb_id') for m in existing_data if m.get('imdb_id')}
                    print(f"Loaded {len(existing_ids)} existing OMDb records.")
                except json.JSONDecodeError:
                    print("Warning: Existing OMDb file is corrupt. Starting fresh.")

        # Filter out IDs that we already have
        ids_to_process = [mid for mid in imdb_ids if mid not in existing_ids]
        print(f"Found {len(ids_to_process)} new movies to fetch from OMDb.")

        if limit > 0:
            ids_to_process = ids_to_process[:limit]
            print(f"Processing a limit of {limit} new movies.")

        for imdb_id in tqdm(ids_to_process, desc="Fetching from OMDb"):
            movie_data = self.fetch_movie_data(imdb_id)
            if movie_data:
                self.enriched_movies.append(self._format_document(movie_data))
            
            # OMDb has a rate limit, a small delay is good practice
            time.sleep(0.05) 
            
            # Save periodically (every 100) to avoid losing data on crash
            if len(self.enriched_movies) % 100 == 0:
                 self.save_data(verbose=False)

    def _format_document(self, data: Dict) -> Dict:
        """Formats the OMDb API response into our standard document structure."""
        
        # Extract ratings, handling different formats
        ratings = {}
        for r in data.get('Ratings', []):
            source = r.get('Source')
            value = r.get('Value')
            if source == 'Internet Movie Database':
                ratings['imdb'] = float(value.split('/')[0])
            elif source == 'Rotten Tomatoes':
                ratings['rotten_tomatoes'] = int(value.replace('%', ''))
            elif source == 'Metacritic':
                ratings['metacritic'] = int(value.split('/')[0])

        return {
            "id": f"omdb_{data.get('imdbID')}",
            "imdb_id": data.get('imdbID'),
            "title": data.get('Title'),
            "year": int(data.get('Year')) if data.get('Year', '').isdigit() else None,
            "genres": data.get('Genre', '').split(', ') if data.get('Genre') else [],
            "plot": data.get('Plot'),
            "directors": data.get('Director', '').split(', ') if data.get('Director') else [],
            "cast": data.get('Actors', '').split(', ') if data.get('Actors') else [],
            "source": "omdb",
            "url": f"https://www.imdb.com/title/{data.get('imdbID')}/",
            "poster": data.get('Poster'),
            "metascore": ratings.get('metacritic'),
            "tomatometer": ratings.get('rotten_tomatoes'),
            # Use IMDb rating from OMDb as it's on a 10-point scale
            "rating": ratings.get('imdb'),
        }

    def save_data(self, verbose=True):
        """Saves the processed movie data to a JSON file."""
        if not self.enriched_movies:
            if verbose: print("No movie data to save.")
            return

        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(self.enriched_movies, f, indent=2, ensure_ascii=False)
        
        if verbose: print(f"Saved {len(self.enriched_movies)} enriched movies to {self.output_file}")


def main():
    """Main execution function."""
    print("Starting OMDb data enrichment process...")
    
    
    processor = OMDbProcessor()
    
    processor.process_movies(limit=800) 
    processor.save_data()
    print("\nOMDb processing complete!")


if __name__ == "__main__":
    main()
