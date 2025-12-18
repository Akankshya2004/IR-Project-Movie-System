"""
Flask web application.
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for
from solr_client import SolrClient
import os
import random


app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-key'

# Initialize Solr client
solr_client = SolrClient()

# Results per page
RESULTS_PER_PAGE = 10


@app.route('/')
def index():
    """Home page with search form."""
    # Get available facet values for filters
    genres = solr_client.get_facet_values('genres', limit=50)
    
    return render_template(
        'index.html',
        genres=genres
    )


@app.route('/search')
def search():
    """
    Search endpoint with faceting and filtering support.
    
    Query parameters:
        q: Search query
        genres: Genre filters (can be multiple)
        year_min: Minimum year
        year_max: Maximum year
        rating_min: Minimum rating
        sort: Sort order
        page: Page number (default: 1)
    """
    # Get search parameters
    query = request.args.get('q', '*:*').strip()
    if not query:
        query = '*:*'
    
    page = int(request.args.get('page', 1))
    start = (page - 1) * RESULTS_PER_PAGE
    
    # Get filters
    filters = {}
    
    # Genre filter (can be multiple)
    selected_genres = request.args.getlist('genres')
    if selected_genres:
        filters['genres'] = selected_genres
    
    # Year range filter
    year_min = request.args.get('year_min', '').strip()
    year_max = request.args.get('year_max', '').strip()
    if year_min or year_max:
        min_val = int(year_min) if year_min else 1900
        max_val = int(year_max) if year_max else 2024
        filters['year'] = (min_val, max_val)
    
    # Rating filter
    rating_min = request.args.get('rating_min', '').strip()
    if rating_min:
        filters['rating'] = (float(rating_min), 10.0)
    
    # Sort order
    sort = request.args.get('sort', '')
    if not sort:
        sort = None  # Use Solr's default relevance ranking
    
    # Perform search with faceting
    results = solr_client.search(
        query=query,
        filters=filters,
        facets=['genres', 'year'],
        sort=sort,
        start=start,
        rows=RESULTS_PER_PAGE,
        highlight=True
    )
    
    # Calculate pagination
    total_results = results['num_found']
    total_pages = (total_results + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
    
    # Process highlighting
    docs_with_highlights = []
    for doc in results['docs']:
        doc_id = doc['id']
        
        # Get plot and reviews, ensuring they are strings
        plot = doc.get('plot', '')
        if isinstance(plot, list):
            plot = plot[0] if plot else ''
            
        reviews = doc.get('reviews', '')
        if isinstance(reviews, list):
            reviews = reviews[0] if reviews else ''

        if doc_id in results.get('highlighting', {}):
            hl = results['highlighting'][doc_id]
            # Highlighting returns a list of snippets, take the first one
            doc['highlighted_plot'] = hl.get('plot', [plot])[0]
            doc['highlighted_reviews'] = hl.get('reviews', [reviews])[0]
        else:
            doc['highlighted_plot'] = plot
            doc['highlighted_reviews'] = reviews

        # Always use the Solr poster field. You guaranteed every doc has a poster,
        # so never fall back to None here.
        poster = doc.get('poster')
        if isinstance(poster, list) and poster:
            doc['poster'] = poster[0]
        else:
            doc['poster'] = poster
        
        # Truncate for display
        if doc['highlighted_plot']:
            doc['snippet'] = doc['highlighted_plot'][:300] + '...' if len(doc['highlighted_plot']) > 300 else doc['highlighted_plot']
        elif doc['highlighted_reviews']:
            doc['snippet'] = doc['highlighted_reviews'][:300] + '...' if len(doc['highlighted_reviews']) > 300 else doc['highlighted_reviews']
        else:
            doc['snippet'] = ''
        
        docs_with_highlights.append(doc)
    
    return render_template(
        'results.html',
        query=query,
        results=docs_with_highlights,
        total_results=total_results,
        page=page,
        total_pages=total_pages,
        results_per_page=RESULTS_PER_PAGE,
        facets=results.get('facets', {}),
        selected_genres=selected_genres,
        year_min=year_min,
        year_max=year_max,
        rating_min=rating_min,
        sort=sort
    )


@app.route('/movie/<movie_id>')
def movie_detail(movie_id):
    """Movie detail page."""
    movie = solr_client.get_by_id(movie_id)
    
    if not movie:
        return render_template('error.html', message=f"Movie with ID '{movie_id}' not found."), 404
    
    # Get similar movies
    similar = solr_client.more_like_this(movie_id, rows=5)
    
    return render_template(
        'movie.html',
        movie=movie,
        similar_movies=similar.get('docs', [])
    )


@app.route('/random')
def random_search():
    """Redirect to a random search result."""
    # Use a random seed for Solr's random sorting
    seed = random.randint(1, 100000)
    return redirect(url_for('search', q='*:*', sort=f'random_{seed} desc'))


@app.route('/similar/<doc_id>')
def similar_movies(doc_id):
    """
    Find and display similar movies using More Like This.
    
    Args:
        doc_id: ID of the source movie
    """
    # Get the source movie
    source_movie = solr_client.get_by_id(doc_id)
    
    if not source_movie:
        return render_template(
            'error.html',
            message=f"Movie with ID '{doc_id}' not found."
        ), 404
    
    # Get similar movies
    similar = solr_client.more_like_this(doc_id, rows=10)
    
    return render_template(
        'similar.html',
        source_movie=source_movie,
        similar_movies=similar['docs'],
        num_similar=similar['num_found']
    )


@app.route('/api/stats')
def api_stats():
    """API endpoint for collection statistics."""
    stats = solr_client.stats()
    return jsonify(stats)


@app.route('/api/autocomplete')
def api_autocomplete():
    """
    API endpoint for search query autocomplete.
    Returns movie titles matching the query prefix.
    """
    prefix = request.args.get('q', '').strip()
    if not prefix or len(prefix) < 2:
        return jsonify([])
    
    # Search for titles starting with prefix
    results = solr_client.search(
        query=f'title:{prefix}*',
        rows=10
    )
    
    suggestions = [
        {
            'title': doc['title'],
            'year': doc.get('year', ''),
            'id': doc['id']
        }
        for doc in results['docs']
    ]
    
    return jsonify(suggestions)


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return render_template('error.html', message="Page not found."), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    return render_template(
        'error.html',
        message="An internal error occurred. Please try again later."
    ), 500


@app.template_filter('truncate_list')
def truncate_list(lst, length=5):
    """Template filter to truncate a list."""
    if not lst:
        return []
    return lst[:length]


@app.template_filter('join_with_comma')
def join_with_comma(lst):
    """Template filter to join list with commas."""
    if not lst:
        return ''
    return ', '.join(str(item) for item in lst)


if __name__ == '__main__':
    # Check if Solr is accessible
    stats = solr_client.stats()
    if stats['status'] == 'error':
        print("WARNING: Cannot connect to Solr!")
        print("Make sure Solr is running: http://localhost:8983/solr/")
        print(f"Error: {stats.get('error', 'Unknown error')}")
        print()
    else:
        print(f"Connected to Solr. Total documents: {stats['total_docs']}")
        print()
    
    # Run Flask app
    print("Starting Movie IR System...")
    print("Open browser to: http://localhost:5001")
    app.run(debug=True, host='0.0.0.0', port=5001)
