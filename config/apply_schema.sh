#!/bin/bash

# Script to apply schema to Solr movies collection using Schema API
# Run this after creating the movies collection

SOLR_URL="http://localhost:8983/solr/movies"

echo "Applying schema to movies collection..."

# Add text_general field type
curl -X POST -H 'Content-type:application/json' \
  "${SOLR_URL}/schema" -d '{
  "add-field-type": {
    "name": "text_general",
    "class": "solr.TextField",
    "positionIncrementGap": "100",
    "indexAnalyzer": {
      "tokenizer": {"class": "solr.StandardTokenizerFactory"},
      "filters": [
        {"class": "solr.LowerCaseFilterFactory"},
        {"class": "solr.StopFilterFactory", "ignoreCase": true, "words": "stopwords.txt"},
        {"class": "solr.PorterStemFilterFactory"}
      ]
    },
    "queryAnalyzer": {
      "tokenizer": {"class": "solr.StandardTokenizerFactory"},
      "filters": [
        {"class": "solr.LowerCaseFilterFactory"},
        {"class": "solr.StopFilterFactory", "ignoreCase": true, "words": "stopwords.txt"},
        {"class": "solr.PorterStemFilterFactory"}
      ]
    }
  }
}'

# Add text_title field type
curl -X POST -H 'Content-type:application/json' \
  "${SOLR_URL}/schema" -d '{
  "add-field-type": {
    "name": "text_title",
    "class": "solr.TextField",
    "positionIncrementGap": "100",
    "analyzer": {
      "tokenizer": {"class": "solr.StandardTokenizerFactory"},
      "filters": [
        {"class": "solr.LowerCaseFilterFactory"},
        {"class": "solr.StopFilterFactory", "ignoreCase": true, "words": "stopwords.txt"}
      ]
    }
  }
}'

# Add fields
curl -X POST -H 'Content-type:application/json' \
  "${SOLR_URL}/schema" -d '{
  "add-field": [
    {"name": "title", "type": "text_title", "stored": true, "indexed": true},
    {"name": "year", "type": "pint", "stored": true, "indexed": true},
    {"name": "genres", "type": "string", "stored": true, "indexed": true, "multiValued": true},
    {"name": "directors", "type": "string", "stored": true, "indexed": true, "multiValued": true},
    {"name": "cast", "type": "string", "stored": true, "indexed": true, "multiValued": true},
    {"name": "site", "type": "string", "stored": true, "indexed": true},
    {"name": "rating", "type": "pfloat", "stored": true, "indexed": true},
    {"name": "num_reviews", "type": "pint", "stored": true, "indexed": true},
    {"name": "plot", "type": "text_general", "stored": true, "indexed": true},
    {"name": "reviews", "type": "text_general", "stored": true, "indexed": true},
    {"name": "url", "type": "string", "stored": true, "indexed": false},
    {"name": "text", "type": "text_general", "stored": false, "indexed": true, "multiValued": true}
  ]
}'

# Add copy fields
curl -X POST -H 'Content-type:application/json' \
  "${SOLR_URL}/schema" -d '{
  "add-copy-field": [
    {"source": "title", "dest": "text"},
    {"source": "plot", "dest": "text"},
    {"source": "reviews", "dest": "text"},
    {"source": "genres", "dest": "text"},
    {"source": "directors", "dest": "text"},
    {"source": "cast", "dest": "text"}
  ]
}'

echo ""
echo "Schema applied successfully!"
echo "You can verify at: ${SOLR_URL}/schema"
