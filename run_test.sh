#!/bin/bash
# run_test.sh

# Set virtual environment
#python3 -m venv venv

# Set variables just for this script
export GAMDL_CONFIG_PATH=~/Documents/config
export GAMDL_MEDIA_PATH=~/Documents/media

# Activate virtual environment
source venv/bin/activate

# Install dependencies
# pip install -r requirements.txt

# Run app
python app.py

# Deactivate virtual environment
# deactivate

# Remove virtual environment
# rm -rf venv

# Clean up on ctrl+C
# trap 'echo -e "\nCleaning up..."; deactivate; rm -rf venv' SIGINT