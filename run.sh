#!/bin/bash

# ==============================================================================
# Movie IR System - Setup Script
# ==============================================================================

# --- Configuration ---
VENV_DIR="venv"

# --- Helper Functions ---
print_header() {
    echo "=========================================="
    echo "Movie IR System - Quick Start"
    echo "=========================================="
}

print_step() {
    echo -e "\n\033[1;34m$1\033[0m"
}

print_success() {
    echo -e "\033[0;32m✓ $1\033[0m"
}

print_warning() {
    echo -e "\033[1;33m⚠ $1\033[0m"
}

print_error() {
    echo -e "\033[0;31m✗ $1\033[0m"
    exit 1
}

# --- Main Execution ---
print_header

# 1. Check for a stable Python version
print_step "Checking for a stable Python version (e.g., 3.12)..."
if command -v python3.12 >/dev/null 2>&1; then
    PYTHON_EXEC="python3.12"
elif command -v python3.11 >/dev/null 2>&1; then
    PYTHON_EXEC="python3.11"
else
    print_warning "Could not find Python 3.12 or 3.11. Defaulting to python3."
    print_warning "If you see build errors, please install Python 3.12 (e.g., 'brew install python@3.12')."
    PYTHON_EXEC="python3"
fi
print_success "Using '$PYTHON_EXEC' for virtual environment."

# 2. Setup and activate virtual environment
if [ ! -d "$VENV_DIR" ]; then
    print_step "Creating Python virtual environment with $PYTHON_EXEC..."
    $PYTHON_EXEC -m venv $VENV_DIR || print_error "Failed to create virtual environment."
    print_success "Virtual environment created."

    print_step "Activating virtual environment..."
    source $VENV_DIR/bin/activate || print_error "Failed to activate virtual environment."
    print_success "Virtual environment activated."

    print_step "Installing Python dependencies..."
    # Upgrade pip first for better compatibility
    pip install --upgrade pip
    pip install -r requirements.txt || print_error "Failed to install Python dependencies."
    print_success "Python dependencies installed"
else
    print_step "Activating existing virtual environment..."
    source $VENV_DIR/bin/activate || print_error "Failed to activate virtual environment."
    print_success "Virtual environment activated."
fi

# 3. Run data processing scripts
print_step "Running data processing scripts..."
# The python scripts will now run using the virtual environment's interpreter

print_step "Step 1: Processing base IMDb data..."
python scrapers/process_imdb_data.py || print_error "IMDb data processing failed."

print_step "Step 2: Enriching with OMDb data..."
python scrapers/process_omdb_data.py || print_error "OMDb data processing failed."

print_step "Step 3: Fetching NYT articles..."
python scrapers/process_nyt_articles.py || print_error "NYT article processing failed."

print_success "Data processing complete"

# 5. Merge all data sources
print_step "Merging data..."
python scrapers/merge_data.py || print_error "Data merging failed."
print_success "Data merge complete"

# 6. Check Solr status and provide indexing command
print_step "Checking Solr status..."
if ! curl -s "http://localhost:8983/solr/admin/collections?action=LIST" | grep -q "movies"; then
    print_warning "Solr does not appear to be running or the 'movies' collection is missing."
    print_warning "Please start Solr and create the 'movies' collection."
else
    print_success "Solr is running"
    print_step "Checking if 'movies' collection exists..."
    print_success "Movies collection exists"
    
    # Check if data is already indexed
    if curl -s "http://localhost:8983/solr/movies/select?q=*:*&rows=0" | grep -q '"numFound":0'; then
        print_warning "No documents indexed. Indexing data..."
        echo -e "\nPlease run the following command from your Solr directory:"
        echo -e "  \033[1;32mbin/post -c movies \"$(pwd)/data/solr/movies.json\"\033[0m\n"
        read -p "Press Enter after indexing is complete..."
    else
        print_success "Movie data already exists"
    fi
fi

# Deactivate virtual environment
deactivate
echo -e "\nAll steps complete. Virtual environment deactivated."
