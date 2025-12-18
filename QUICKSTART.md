# Quick Start Guide

This guide will help you get the Movie IR System up and running.

## Prerequisites

- Python 3.8 or higher
- Apache Solr 9.x
- 2GB free disk space
- Internet connection (for scraping data)

## Step-by-Step Setup

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Install and Configure Solr

#### Option A: Using Homebrew (macOS)
```bash
brew install solr
solr start
```

#### Option B: Manual Installation
```bash
# Download Solr 9.x from https://solr.apache.org/downloads.html
tar xzf solr-9.x.x.tgz
cd solr-9.x.x
bin/solr start
```

### 3. Create Solr Collection and Apply Schema

```bash
# Create the movies collection
bin/solr create -c movies

# Apply the schema
chmod +x apply_schema.sh
./apply_schema.sh
```

Verify in browser: http://localhost:8983/solr/#/movies

### 4. Scrape and Prepare Data

```bash
# Run scrapers and processors
python scrapers/process_imdb_data.py
python scrapers/process_omdb_data.py
python scrapers/scrape_roger_ebert.py

# Merge data into single file
python scrapers/merge_data.py
```

This will create `data/solr/movies.json` with the processed movie data.

### 5. Index Data in Solr

From your Solr installation directory:

```bash
bin/post -c movies "Project/data/solr/movies.json"
```

Verify indexing:
- Open: http://localhost:8983/solr/#/movies/query
- Click "Execute Query"
- You should see movie documents in the response

### 6. Run the Web Application

```bash
cd web
python app.py
```

Open your browser to: **http://localhost:5001**

## Using the Quick Start Script

Alternatively, use the automated setup script:

```bash
./run.sh
```

This script will:
1. Check prerequisites
2. Install dependencies
3. Verify Solr is running
4. Run scrapers if needed
5. Check data indexing
6. Start the web application

## Testing the System

### Test Basic Search
1. Go to http://localhost:5001
2. Search for "inception"
3. You should see results

### Test Faceted Search
1. Click "Advanced Filters"
2. Select genre "Action"
3. Set year range: 2010-2020
4. Set minimum rating: 8.0
5. Click "Search" or "Apply Filters"

### Test More Like This
1. Search for any movie
2. Click "Find Similar Movies" on a result
3. You should see similar movies based on plot, genre, and cast

## Troubleshooting

### Solr Not Running
```bash
# Check status
curl http://localhost:8983/solr/

# Start Solr
cd <solr-directory>
bin/solr start
```

### Port 8983 Already in Use
```bash
# Find and kill process
lsof -ti:8983 | xargs kill -9

# Or start Solr on different port
bin/solr start -p 8984
# Then update solr_client.py to use new port
```

### No Movies in Search Results
```bash
# Check if documents are indexed
curl "http://localhost:8983/solr/movies/select?q=*:*&rows=0"

# Look for "numFound" in response
# If 0, re-run indexing step
```

### Flask Port 5001 in Use
```bash
# Edit web/app.py, change last line:
app.run(debug=True, host='0.0.0.0', port=5002)
```

### Module Not Found Errors
```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```
