/**
 * Main JavaScript file
 */

document.addEventListener('DOMContentLoaded', function() {
    initSearchEnhancements();
    initResponsiveFeatures();
});

function initSearchEnhancements() {
    const searchInput = document.querySelector('.search-input');
    
    if (searchInput) {
        // Ctrl/Cmd + K to focus search
        document.addEventListener('keydown', function(e) {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                searchInput.focus();
            }
        });
    }
}

/*
 * Autocomplete functionality
 */
function initAutocomplete(inputElement) {
    let timeout = null;
    
    inputElement.addEventListener('input', function(e) {
        clearTimeout(timeout);
        const query = e.target.value.trim();
        
        if (query.length < 2) {
            hideAutocomplete();
            return;
        }
        
        timeout = setTimeout(() => {
            fetchSuggestions(query);
        }, 300);
    });
}

function fetchSuggestions(query) {
    fetch(`/api/autocomplete?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(suggestions => {
            showAutocomplete(suggestions);
        })
        .catch(error => {
            console.error('Autocomplete error:', error);
        });
}

function showAutocomplete(suggestions) {
    hideAutocomplete();
    
    if (suggestions.length === 0) return;
    
    const searchBox = document.querySelector('.search-box');
    const dropdown = document.createElement('div');
    dropdown.className = 'autocomplete-dropdown';
    dropdown.id = 'autocomplete-dropdown';
    
    suggestions.forEach(item => {
        const option = document.createElement('a');
        option.href = `/search?q=${encodeURIComponent(item.title)}`;
        option.className = 'autocomplete-item';
        option.innerHTML = `
            <strong>${item.title}</strong>
            <span>${item.year}</span>
        `;
        dropdown.appendChild(option);
    });
    
    searchBox.appendChild(dropdown);
}

function hideAutocomplete() {
    const dropdown = document.getElementById('autocomplete-dropdown');
    if (dropdown) {
        dropdown.remove();
    }
}

/**
 * Responsive features
 */
function initResponsiveFeatures() {
    // Smooth scroll to top button
    const scrollButton = createScrollToTopButton();
    
    window.addEventListener('scroll', function() {
        if (window.pageYOffset > 300) {
            scrollButton.style.display = 'block';
        } else {
            scrollButton.style.display = 'none';
        }
    });
    
    scrollButton.addEventListener('click', function() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });
}

function createScrollToTopButton() {
    const button = document.createElement('button');
    button.innerHTML = '↑';
    button.className = 'scroll-to-top';
    button.style.cssText = `
        position: fixed;
        bottom: 30px;
        right: 30px;
        background-color: #3498db;
        color: white;
        border: none;
        border-radius: 50%;
        width: 50px;
        height: 50px;
        font-size: 24px;
        cursor: pointer;
        display: none;
        box-shadow: 0 4px 10px rgba(0,0,0,0.3);
        z-index: 1000;
        transition: background-color 0.3s;
    `;
    
    button.addEventListener('mouseenter', function() {
        this.style.backgroundColor = '#2980b9';
    });
    
    button.addEventListener('mouseleave', function() {
        this.style.backgroundColor = '#3498db';
    });
    
    document.body.appendChild(button);
    return button;
}

/**
 * Utility function to highlight search terms in results
 */
function highlightTerms(text, terms) {
    if (!terms || terms.length === 0) return text;
    
    let highlighted = text;
    terms.forEach(term => {
        const regex = new RegExp(`(${term})`, 'gi');
        highlighted = highlighted.replace(regex, '<mark>$1</mark>');
    });
    
    return highlighted;
}

/**
 * Format rating display
 */
function formatRating(rating) {
    return `⭐ ${rating.toFixed(1)}/10`;
}

/**
 * Truncate text to specified length
 */
function truncateText(text, maxLength = 200) {
    if (text.length <= maxLength) return text;
    return text.substr(0, maxLength).trim() + '...';
}

/**
 * Show loading indicator
 */
function showLoading(element) {
    const loader = document.createElement('div');
    loader.className = 'loading-spinner';
    loader.innerHTML = '<div class="spinner"></div>';
    element.appendChild(loader);
}

/**
 * Hide loading indicator
 */
function hideLoading(element) {
    const loader = element.querySelector('.loading-spinner');
    if (loader) {
        loader.remove();
    }
}
