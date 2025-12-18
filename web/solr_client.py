"""
Solr client interface.
"""

import pysolr
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode


class SolrClient:
    """Interface for querying Solr movies collection."""
    
    def __init__(self, solr_url: str = 'http://localhost:8983/solr/movies'):
        self.solr = pysolr.Solr(solr_url, always_commit=True, timeout=10)
        self.solr_url = solr_url
    
    def search(
        self,
        query: str = '*:*',
        filters: Optional[Dict[str, Any]] = None,
        facets: Optional[List[str]] = None,
        sort: Optional[str] = None,
        start: int = 0,
        rows: int = 10,
        highlight: bool = False
    ) -> Dict:
        """Perform a search query on Solr."""
        # Build base params
        is_match_all = (not query) or (query == '*:*')

        fields = 'id,title,year,rating,tomatometer,genres,directors,cast,plot,reviews,url,site,num_reviews,poster'

        if is_match_all:
            params = {
                'q': '*:*',
                'start': start,
                'rows': rows,
                'fl': fields,
            }
        else:
            # Use Extended DisMax parser to weight fields, especially title
            params = {
                'defType': 'edismax',
                'q': query,
                # Query fields with boosts: title highest, then plot/reviews, then cast/directors/genres
                'qf': 'title^10 cast^5 directors^5 plot^2 reviews^2 genres',
                # Phrase boosts so exact phrases in title/plot/reviews are strongly preferred
                'pf': 'title^25 cast^10 directors^10 plot^3 reviews^3',
                'start': start,
                'rows': rows,
                'fl': fields,
            }

        # Add sort
        if sort:
            params['sort'] = sort

        # Add filter queries
        if filters:
            fq_list = []
            for field, value in filters.items():
                if isinstance(value, list):
                    # Multiple values for same field (OR)
                    or_clauses = [f'{field}:"{v}"' for v in value]
                    fq_list.append(f"({' OR '.join(or_clauses)})")
                elif isinstance(value, tuple) and len(value) == 2:
                    # Range query (e.g., year:[2000 TO 2024])
                    fq_list.append(f'{field}:[{value[0]} TO {value[1]}]')
                else:
                    fq_list.append(f'{field}:"{value}"')
            params['fq'] = fq_list

        # Add faceting
        if facets:
            params['facet'] = 'true'
            params['facet.field'] = facets
            params['facet.mincount'] = 1
            params['facet.limit'] = 20

        # Add highlighting
        if highlight:
            params['hl'] = 'true'
            params['hl.fl'] = 'plot,reviews'
            params['hl.simple.pre'] = '<mark>'
            params['hl.simple.post'] = '</mark>'
            params['hl.fragsize'] = 200

        # Execute search
        try:
            results = self.solr.search(**params)
            
            # Process facets
            processed_facets = {}
            if hasattr(results, 'facets') and 'facet_fields' in results.facets:
                for field, values in results.facets['facet_fields'].items():
                    processed_facets[field] = [
                        {'value': val, 'count': count}
                        for val, count in zip(values[0::2], values[1::2])
                    ]
            
            # Parse response
            response = {
                'docs': results.docs,
                'num_found': results.hits,
                'facets': processed_facets,
                'highlighting': results.highlighting if hasattr(results, 'highlighting') else {}
            }
            
            return response
            
        except Exception as e:
            print(f"Solr search error: {e}")
            return {'docs': [], 'num_found': 0, 'facets': {}}

    def get_movie(self, movie_id: str) -> Dict[str, Any]:
        """
        Fetch a single movie by ID, including similar movies (More Like This).
        
        Args:
            movie_id: The Solr ID of the movie.
            
        Returns:
            Dictionary containing 'doc' (movie details) and 'similar' (list of similar movies).
        """
        try:
            # We use the standard search handler but enable MLT
            params = {
                'q': f'id:"{movie_id}"',
                'rows': 1,
                'fl': '*,score',  # Fetch all fields
                'mlt': 'true',
                'mlt.fl': 'title,plot,reviews,genres,directors,cast',
                'mlt.mindf': 1,
                'mlt.mintf': 1,
                'mlt.count': 5,
                'mlt.boost': 'true',
            }
            
            results = self.solr.search(**params)
            
            if not results.docs:
                return None
                
            doc = results.docs[0]
            
            # Extract MLT results
            # pysolr puts mlt results in results.moreLikeThis[movie_id]['docs']
            similar = []
            if hasattr(results, 'moreLikeThis') and movie_id in results.moreLikeThis:
                similar = results.moreLikeThis[movie_id]['docs']
                
            return {
                'doc': doc,
                'similar': similar
            }
            
        except Exception as e:
            print(f"Error fetching movie {movie_id}: {e}")
            return None

    def get_facet_values(self, field: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get available values for a facet field."""
        try:
            params = {
                'q': '*:*',
                'rows': 0,
                'facet': 'true',
                'facet.field': field,
                'facet.limit': limit,
                'facet.mincount': 1
            }
            
            results = self.solr.search(**params)
            
            if hasattr(results, 'facets') and 'facet_fields' in results.facets:
                # pysolr returns facets as a flat list [val1, count1, val2, count2...]
                # We convert it to [{'value': val, 'count': count}, ...]
                flat_list = results.facets['facet_fields'].get(field, [])
                return [{'value': val, 'count': count} for val, count in zip(flat_list[0::2], flat_list[1::2])]
            
            return []
            
        except Exception as e:
            print(f"Error fetching facets for {field}: {e}")
            return []
    
    def more_like_this(
        self,
        doc_id: str,
        mlt_fields: List[str] = None,
        rows: int = 5
    ) -> Dict:
        """
        Find similar movies using MoreLikeThis.
        
        Args:
            doc_id: ID of the document to find similar items for
            mlt_fields: Fields to use for similarity (default: text, genres, cast, directors)
            rows: Number of similar movies to return
            
        Returns:
            Dictionary with similar movies
        """
        if mlt_fields is None:
            # Use fields that actually exist in our data
            mlt_fields = ['plot', 'title', 'genres', 'cast', 'directors', 'reviews']
        
        params = {
            'q': f'id:{doc_id}',
            'mlt': 'true',
            'mlt.fl': ','.join(mlt_fields),
            'mlt.mindf': 1,
            'mlt.mintf': 1,
            'mlt.count': rows,
            'mlt.interestingTerms': 'details',
            'fl': 'id,title,year,rating,genres,directors,cast,plot,url,site,poster',
        }
        
        try:
            results = self.solr.search(**params)
            
            # Extract MLT results
            similar_docs = []
            
            # Check raw_response for moreLikeThis as pysolr might not parse it
            if hasattr(results, 'raw_response') and 'moreLikeThis' in results.raw_response:
                mlt_data = results.raw_response['moreLikeThis'].get(doc_id, {})
                if isinstance(mlt_data, dict):
                    similar_docs = mlt_data.get('docs', [])
                else:
                    similar_docs = list(mlt_data)
            elif hasattr(results, 'moreLikeThis') and results.moreLikeThis:
                mlt_data = results.moreLikeThis.get(doc_id, {})
                if isinstance(mlt_data, dict):
                    similar_docs = mlt_data.get('docs', [])
                else:
                    similar_docs = list(mlt_data)
            
            return {
                'docs': similar_docs,
                'num_found': len(similar_docs),
                'source_id': doc_id
            }
            
        except Exception as e:
            print(f"MoreLikeThis error: {e}")
            return {
                'docs': [],
                'num_found': 0,
                'error': str(e)
            }
    
    def get_by_id(self, doc_id: str) -> Optional[Dict]:
        """
        Get a specific movie by ID.
        
        Args:
            doc_id: Document ID
            
        Returns:
            Movie document or None if not found
        """
        try:
            results = self.solr.search(q=f'id:{doc_id}', rows=1)
            if results.docs:
                return results.docs[0]
            return None
        except Exception as e:
            print(f"Get by ID error: {e}")
            return None
    
    def _parse_facets(self, facet_data: Dict) -> Dict:
        """
        Parse facet data from Solr response.
        
        Args:
            facet_data: Raw facet data from Solr
            
        Returns:
            Parsed facet dictionary
        """
        if not facet_data or 'facet_fields' not in facet_data:
            return {}
        
        parsed_facets = {}
        for field, values in facet_data['facet_fields'].items():
            # Solr returns facets as [value1, count1, value2, count2, ...]
            facet_list = []
            for i in range(0, len(values), 2):
                if i + 1 < len(values):
                    facet_list.append({
                        'value': values[i],
                        'count': values[i + 1]
                    })
            parsed_facets[field] = facet_list
        
        return parsed_facets
    
    def stats(self) -> Dict:
        """
        Get collection statistics.
        
        Returns:
            Dictionary with collection stats
        """
        try:
            results = self.solr.search(q='*:*', rows=0)
            return {
                'total_docs': results.hits,
                'status': 'ok'
            }
        except Exception as e:
            return {
                'total_docs': 0,
                'status': 'error',
                'error': str(e)
            }
