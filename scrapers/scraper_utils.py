"""
Common utilities for web scraping.
"""

import time
import re
import hashlib
from typing import Optional, List
import requests
from bs4 import BeautifulSoup


class ScraperUtils:
    """Utility class for common scraping operations."""
    
    # User agent to appear as a regular browser
    USER_AGENT = (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
    
    @staticmethod
    def get_page(url: str, delay: float = 1.0) -> Optional[BeautifulSoup]:
        """
        Fetch a web page and return parsed BeautifulSoup object.
        
        Args:
            url: URL to fetch
            delay: Seconds to wait before request (respectful crawling)
            
        Returns:
            BeautifulSoup object or None if request fails
        """
        time.sleep(delay)  # Respectful crawling
        
        try:
            headers = {'User-Agent': ScraperUtils.USER_AGENT}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'lxml')
        except requests.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    @staticmethod
    def clean_text(text: Optional[str]) -> str:
        """
        Clean HTML text by removing extra whitespace and newlines.
        
        Args:
            text: Raw text string
            
        Returns:
            Cleaned text string
        """
        if not text:
            return ""
        
        # Remove extra whitespace and newlines
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    @staticmethod
    def extract_year(text: str) -> Optional[int]:
        """
        Extract a 4-digit year from text.
        
        Args:
            text: Text containing a year
            
        Returns:
            Year as integer or None if not found
        """
        match = re.search(r'(19|20)\d{2}', text)
        if match:
            return int(match.group())
        return None
    
    @staticmethod
    def normalize_rating(rating: float, max_rating: float = 10.0) -> float:
        """
        Normalize rating to 0-10 scale.
        
        Args:
            rating: Original rating value
            max_rating: Maximum value in original scale
            
        Returns:
            Rating normalized to 0-10 scale
        """
        if max_rating == 0:
            return 0.0
        return round((rating / max_rating) * 10.0, 1)
    
    @staticmethod
    def generate_id(text: str, prefix: str = "") -> str:
        """
        Generate a unique ID from text using hash.
        
        Args:
            text: Text to hash (e.g., movie title + year)
            prefix: Optional prefix for the ID
            
        Returns:
            Unique ID string
        """
        hash_object = hashlib.md5(text.encode())
        hash_hex = hash_object.hexdigest()[:12]
        return f"{prefix}_{hash_hex}" if prefix else hash_hex
    
    @staticmethod
    def extract_number(text: str) -> Optional[int]:
        """
        Extract a number from text (e.g., "1,234 reviews" -> 1234).
        
        Args:
            text: Text containing a number
            
        Returns:
            Extracted number or None
        """
        # Remove commas and extract digits
        match = re.search(r'[\d,]+', text)
        if match:
            number_str = match.group().replace(',', '')
            try:
                return int(number_str)
            except ValueError:
                pass
        return None
    
    @staticmethod
    def split_list(text: str, delimiter: str = ',') -> List[str]:
        """
        Split text into list and clean each item.
        
        Args:
            text: Delimited text string
            delimiter: Delimiter character
            
        Returns:
            List of cleaned strings
        """
        if not text:
            return []
        return [item.strip() for item in text.split(delimiter) if item.strip()]
    
    @staticmethod
    def truncate_text(text: str, max_length: int = 500) -> str:
        """
        Truncate text to maximum length, ending at word boundary.
        
        Args:
            text: Text to truncate
            max_length: Maximum character length
            
        Returns:
            Truncated text
        """
        if len(text) <= max_length:
            return text
        
        # Find last space before max_length
        truncated = text[:max_length].rsplit(' ', 1)[0]
        return truncated + '...'


def create_movie_document(
    title: str,
    year: int,
    site: str,
    url: str,
    rating: float = None,
    genres: List[str] = None,
    directors: List[str] = None,
    cast: List[str] = None,
    plot: str = "",
    reviews: str = "",
    num_reviews: int = None
) -> dict:
    """
    Create a standardized movie document for Solr indexing.
    
    Args:
        title: Movie title
        year: Release year
        site: Source website
        url: Original URL
        rating: Normalized rating (0-10)
        genres: List of genres
        directors: List of directors
        cast: List of cast members
        plot: Plot summary
        reviews: Concatenated review text
        num_reviews: Number of reviews
        
    Returns:
        Dictionary ready for Solr indexing
    """
    # Generate unique ID from title, year, and site
    id_text = f"{title}_{year}_{site}"
    doc_id = ScraperUtils.generate_id(id_text, site)
    
    return {
        'id': doc_id,
        'title': title,
        'year': year,
        'site': site,
        'url': url,
        'rating': rating,
        'genres': genres or [],
        'directors': directors or [],
        'cast': cast or [],
        'plot': plot,
        'reviews': reviews,
        'num_reviews': num_reviews
    }
