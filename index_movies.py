import json

import pysolr


SOLR_URL = "http://localhost:8983/solr/movies"


def main() -> None:
    """Reindex data/solr/movies.json into the Solr 'movies' collection."""
    solr = pysolr.Solr(SOLR_URL, always_commit=True, timeout=30)

    # Load JSON file
    with open("data/solr/movies.json", "r", encoding="utf-8") as f:
        movies = json.load(f)

    print(f"Loaded {len(movies)} movies from data/solr/movies.json")

    # Delete existing docs
    print("Deleting existing docs from 'movies' collection...")
    solr.delete(q="*:*")

    print("Indexing documents into Solr...")
    batch_size = 1000
    for i in range(0, len(movies), batch_size):
        batch = movies[i : i + batch_size]
        solr.add(batch)
        print(f"Indexed {i + len(batch)}/{len(movies)}")

    print("Done reindexing movies.")


if __name__ == "__main__":
    main()
