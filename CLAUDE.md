# Cabinet Door Generator

## Project Overview
Streamlit app that generates cabinet door image variations across different wood types using Google Gemini 3's image generation with "thought signatures" for style consistency.

## Architecture
- `generator.py` - Core `DoorGenerator` class wrapping Gemini 3 Pro Image API
- `app.py` - Streamlit UI with 3-step workflow (upload → select woods → generate)
- `swatches/` - Wood swatch reference images
- `output/` - Generated images (gitignored)

## Key Concept: Thought Signatures
Gemini returns a binary "thought signature" when generating images. This signature encodes the model's understanding of the door style and can be passed back in subsequent requests to maintain geometric consistency while changing materials.

## Commands
```bash
uv run streamlit run app.py    # Run the app
uv run ruff check .            # Lint
uv run ruff format .           # Format
```

## Environment
- Requires `GEMINI_API_KEY` env var (or enter in sidebar)
- Python 3.12+
- Uses uv for dependency management

## Cost
~$0.134 per image generated (Gemini 3 Pro Image, 1K-2K resolution)
