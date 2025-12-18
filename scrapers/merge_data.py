"""
Merges movie data from multiple sources into a single file for Solr.

Sources:
1. IMDb
2. OMDb
3. Roger Ebert Reviews

Output: movies.json
"""

import json
import os
from typing import List, Dict, Any
from collections import defaultdict


class DataMerger:
    """Merges and enriches movie data from various sources."""

    def __init__(self, base_data_path: str, output_path: str):
        self.base_path = base_data_path
        self.output_path = output_path
        self.movies: Dict[str, Dict[str, Any]] = {}
        self.nyt_articles: Dict[str, List[Dict]] = defaultdict(list)
        self.omdb_data: Dict[str, Dict] = {}
        self.rt_data: Dict[str, Dict] = {}
        self.rogerebert_data: Dict[str, Dict] = {}
        self.rogerebert_title_map: Dict[str, List[Dict]] = defaultdict(list)

    def load_data(self):
        """Loads all source data into memory."""
        print("Loading all data sources...")
        
        # 1. Load base IMDb movies, keyed by IMDb ID
        imdb_movies = self._load_json(os.path.join(self.base_path, 'imdb_movies.json'))
        for movie in imdb_movies:
            if 'tconst' in movie:
                self.movies[movie['tconst']] = movie

        # 2. Load OMDb data, keyed by IMDb ID
        omdb_movies = self._load_json(os.path.join(self.base_path, 'omdb_movies.json'))
        for movie in omdb_movies:
            if 'imdb_id' in movie:
                self.omdb_data[movie['imdb_id']] = movie

        # # 3. Load NYT articles, grouped by IMDb ID -- depricated
        # nyt_articles = self._load_json(os.path.join(self.base_path, 'nyt_articles.json'))
        # for article in nyt_articles:
        #     if 'imdb_id' in article:
        #         self.nyt_articles[article['imdb_id']].append(article)
        
        # 4. Load Rotten Tomatoes sample data, keyed by (title, year)
        rt_movies = self._load_json(os.path.join(self.base_path, 'rottentomatoes_movies.json'))
        for movie in rt_movies:
            if 'title' in movie and 'year' in movie:
                key = self._get_title_year_key(movie['title'], movie['year'])
                self.rt_data[key] = movie

        # 5. Load Roger Ebert reviews, keyed by (title, year)
        re_reviews = self._load_json(os.path.join(self.base_path, 'rogerebert_reviews.json'))
        for movie in re_reviews:
            if 'title' in movie:
                # Use year if available, otherwise just title might be risky but we'll try
                year = movie.get('year', 0)
                key = self._get_title_year_key(movie['title'], year)
                self.rogerebert_data[key] = movie
                
                # Fallback: Store by title for fuzzy matching (especially if year is 0)
                clean_title = movie['title'].lower().strip()
                self.rogerebert_title_map[clean_title].append(movie)

        print(f"Loaded {len(self.movies)} base movies.")
        print(f"Loaded {len(self.omdb_data)} OMDb records for enrichment.")
        print(f"Loaded {len(self.nyt_articles)} NYT article lists.")
        print(f"Loaded {len(self.rogerebert_data)} Roger Ebert reviews.")

    def _load_json(self, filepath: str) -> List[Dict]:
        """Safely loads a JSON file."""
        if not os.path.exists(filepath):
            print(f"Warning: {filepath} not found, skipping...")
            return []
        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON from {filepath}: {e}")
                return []

    def _get_title_year_key(self, title: str, year: int) -> str:
        """Creates a consistent key from title and year."""
        return f"{title.lower()}_{year}"

    def process_and_merge(self):
        """Merges all loaded data into the final movie documents."""
        print("Starting merge and enrichment process...")
        
        # Create a lookup for existing movies by title_year to match external data
        title_year_map = {}
        for imdb_id, movie in self.movies.items():
            # Check for both naming conventions (raw TSV vs processed JSON)
            title = movie.get('primaryTitle') or movie.get('title')
            year_val = movie.get('startYear') or movie.get('year')
            
            if title and year_val:
                try:
                    year = int(year_val)
                    key = self._get_title_year_key(title, year)
                    title_year_map[key] = imdb_id
                except (ValueError, TypeError):
                    pass

        for imdb_id, movie in self.movies.items():
            # Merge OMDb data
            if imdb_id in self.omdb_data:
                omdb_record = self.omdb_data[imdb_id]
                movie['metascore'] = omdb_record.get('metascore')
                movie['tomatometer'] = omdb_record.get('tomatometer')
                movie['poster'] = omdb_record.get('poster')
                # OMDb plot is often better
                if omdb_record.get('plot'):
                    movie['plot'] = omdb_record['plot']

            # Merge NYT articles
            if imdb_id in self.nyt_articles:
                articles = self.nyt_articles[imdb_id]
                movie['nyt_reviews_headlines'] = [a.get('headline') for a in articles if a.get('headline')]
                movie['nyt_reviews_abstracts'] = [a.get('abstract') for a in articles if a.get('abstract')]
                movie['nyt_reviews_snippets'] = [a.get('snippet') for a in articles if a.get('snippet')]
            
            # Merge Roger Ebert Reviews
            # Try to match by title/year
            title = movie.get('primaryTitle') or movie.get('title')
            year_val = movie.get('startYear') or movie.get('year')
            
            if title and year_val:
                try:
                    year = int(year_val)
                    key = self._get_title_year_key(title, year)
                    re_data = self.rogerebert_data.get(key)
                    
                    # Fallback: Try title-only match if exact match failed
                    if not re_data:
                        candidates = self.rogerebert_title_map.get(title.lower().strip())
                        if candidates:
                            for cand in candidates:
                                cand_year = cand.get('year', 0)
                                # Match if year is 0 (missing) or within 1 year
                                if cand_year == 0 or abs(cand_year - year) <= 1:
                                    re_data = cand
                                    break

                    if re_data:
                        movie['rogerebert_review'] = re_data.get('reviews')
                        movie['rogerebert_critic'] = re_data.get('critic')
                        movie['rogerebert_rating'] = re_data.get('rating')
                        movie['rogerebert_url'] = re_data.get('url')
                        # Append to generic reviews field if it exists or create it
                        if 'reviews' not in movie:
                            movie['reviews'] = []
                        if isinstance(movie['reviews'], list):
                            movie['reviews'].append(re_data.get('reviews', ''))
                        elif isinstance(movie['reviews'], str):
                             movie['reviews'] = [movie['reviews'], re_data.get('reviews', '')]

                except (ValueError, TypeError):
                    pass

            # Finalize ID and source field
            movie['id'] = movie.get('tconst') # Use IMDb ID as the unique Solr ID
            movie['source'] = ['imdb']
            if imdb_id in self.omdb_data:
                movie['source'].append('omdb')
            if imdb_id in self.nyt_articles:
                movie['source'].append('nyt')
            if 'rogerebert_review' in movie:
                movie['source'].append('rogerebert')
            
            # Clean up redundant fields
            movie.pop('tconst', None)
        

        print(f"Merge complete. Total movies to be saved: {len(self.movies)}")

    def save_merged_data(self):
        """Saves the final merged data to the output JSON file."""
        if not self.movies:
            print("No data to save.")
            return

        final_movie_list = list(self.movies.values())
        
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        with open(self.output_path, 'w', encoding='utf-8') as f:
            json.dump(final_movie_list, f, indent=2, ensure_ascii=False)
        print(f"Successfully saved merged data to {self.output_path}")


def main():
    """Main execution function."""
    print("Starting data merging and enrichment process...")
    
    base_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw')
    output_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'solr', 'movies.json')
    
    merger = DataMerger(base_data_path=base_path, output_path=output_file)
    merger.load_data()
    merger.process_and_merge()
    merger.save_merged_data()
    
    print("\nData merging complete!")


if __name__ == "__main__":
    main()
