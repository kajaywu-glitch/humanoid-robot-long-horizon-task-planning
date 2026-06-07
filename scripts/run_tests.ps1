$ErrorActionPreference = "Stop"

python -m unittest discover -s tests -v
python scripts/validate_workspace.py

