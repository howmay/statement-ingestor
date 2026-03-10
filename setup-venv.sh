#!/bin/bash
# Setup virtual environment for Gmail Expense Parser

set -e

echo "Setting up Gmail Expense Parser virtual environment..."

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found. Please install Python 3.8 or higher."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python version: $PYTHON_VERSION"

# Remove existing venv if requested
if [[ "$1" == "--clean" ]]; then
    echo "Removing existing virtual environment..."
    rm -rf venv
fi

# Create virtual environment
if [[ ! -d "venv" ]]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
else
    echo "Virtual environment already exists."
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
if [[ "$1" == "--dev" ]] || [[ "$2" == "--dev" ]]; then
    echo "Installing development dependencies..."
    pip install -e ".[dev]"
else
    echo "Installing production dependencies..."
    pip install -e .
fi

# Create .env file if it doesn't exist
if [[ ! -f ".env" ]]; then
    echo "Creating .env file from example..."
    if [[ -f ".env.example" ]]; then
        cp .env.example .env
        echo "Please update .env file with your configuration."
    else
        echo "Warning: .env.example not found. Creating empty .env file."
        touch .env
    fi
fi

# Create config directory if it doesn't exist
if [[ ! -d "config" ]]; then
    echo "Creating config directory..."
    mkdir -p config
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "To activate the virtual environment:"
echo "  source venv/bin/activate"
echo ""
echo "To run the application:"
echo "  python main.py"
echo ""
echo "For development, install additional tools:"
echo "  pip install -r requirements-dev.txt"
echo ""
echo "Don't forget to:"
echo "1. Configure your .env file"
echo "2. Set up Google OAuth2 credentials (see config/README.md)"
echo "3. Place client_secrets.json in config/ directory"