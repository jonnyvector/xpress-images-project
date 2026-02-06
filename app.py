"""Streamlit UI for cabinet door image generation."""

import io
import json
import os
import zipfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import streamlit as st  # noqa: E402
from PIL import Image  # noqa: E402

from generator import DoorGenerator  # noqa: E402

# Page config
st.set_page_config(
    page_title="Cabinet Door Generator",
    page_icon=":wood:",
    layout="wide",
)

# Responsive CSS for medium-small screens
st.markdown(
    """
    <style>
    /* Stack columns on smaller screens */
    @media (max-width: 1200px) {
        [data-testid="stHorizontalBlock"] {
            flex-direction: column;
        }
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            width: 100% !important;
            flex: 1 1 100% !important;
        }
    }
    /* Reduce padding on smaller screens */
    @media (max-width: 768px) {
        .block-container {
            padding: 1rem !important;
        }
        h1 { font-size: 1.75rem !important; }
        h2 { font-size: 1.25rem !important; }
    }
    /* Swatch grid adjustments */
    @media (max-width: 600px) {
        [data-testid="stImage"] {
            max-width: 100% !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Constants
SWATCHES_DIR = Path("swatches")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


def get_swatch_files() -> list[Path]:
    """Get all image files from the swatches directory."""
    if not SWATCHES_DIR.exists():
        return []
    extensions = {".jpg", ".jpeg", ".png", ".webp"}
    return sorted([f for f in SWATCHES_DIR.iterdir() if f.suffix.lower() in extensions])


def load_wood_types() -> dict[str, dict]:
    """Load wood type metadata from JSON file."""
    json_path = SWATCHES_DIR / "wood_types.json"
    if json_path.exists():
        with open(json_path) as f:
            return json.load(f)
    return {}


def get_wood_description(swatch_path: Path, wood_types: dict[str, dict]) -> str | None:
    """Get description for a wood type by matching swatch filename to JSON key."""
    # Normalize: lowercase and convert underscores to hyphens
    key = swatch_path.stem.lower().replace("_", "-")
    if key in wood_types:
        return wood_types[key].get("description") or None
    return None


def swatch_name_from_path(path: Path) -> str:
    """Extract a display name from swatch file path."""
    return path.stem.replace("_", " ").replace("-", " ").title()


def create_zip(results: list[tuple[str, bytes]], door_name: str) -> bytes:
    """Create a ZIP file from generation results."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for wood_name, image_data in results:
            filename = f"{door_name}_{wood_name.lower().replace(' ', '_')}.png"
            zf.writestr(filename, image_data)
    return zip_buffer.getvalue()


def main() -> None:
    """Main application."""
    st.title("Cabinet Door Generator")
    st.markdown("Generate door style variations across different wood types")

    # Sidebar for API key
    with st.sidebar:
        st.header("Settings")
        env_api_key = os.environ.get("GEMINI_API_KEY", "")
        if env_api_key:
            api_key = env_api_key
            st.success("Using API key from environment")
        else:
            api_key = st.text_input(
                "Gemini API Key",
                type="password",
                help="Your Google Gemini API key. "
                "Set GEMINI_API_KEY env var to avoid entering each time.",
            )
            if not api_key:
                st.warning("Enter your API key to enable generation")

        # Transparent background toggle
        remove_bg = st.toggle(
            "Transparent background",
            value=False,
            help="Remove white background from generated images (adds ~3s per image)",
        )

        # Reset button
        if st.button("Reset All", use_container_width=True):
            for key in [
                "learned_signature",
                "learned_aspect_ratio",
                "base_door_image",
                "generation_results",
                "generation_errors",
                "door_name",
            ]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

    # Main layout: two columns
    col_left, col_right = st.columns([1, 2])

    with col_left:
        # Step 1: Upload and Learn Door
        st.header("1. Upload & Learn Door Style")
        uploaded_door = st.file_uploader(
            "Choose a door image",
            type=["jpg", "jpeg", "png", "webp"],
            key="door_upload",
        )

        if uploaded_door:
            st.image(uploaded_door, caption="Your Door", use_container_width=True)
            door_name = st.text_input(
                "Door style name",
                value=Path(uploaded_door.name).stem,
                help="Used for output filenames",
            )

            # Aspect ratio selector
            aspect_options = [
                "3:4 (tall)",
                "9:16 (very tall)",
                "1:1 (square)",
                "4:3 (wide)",
                "16:9 (very wide)",
            ]
            aspect_ratio_choice = st.selectbox(
                "Door aspect ratio",
                options=aspect_options,
                index=0,  # Default to 3:4 for typical cabinet doors
                help="Match your door's shape",
            )
            # Extract just the ratio part
            selected_aspect_ratio = aspect_ratio_choice.split(" ")[0]

            # Learn button
            can_learn = api_key and uploaded_door
            learn_btn = st.button(
                "Learn Door Style",
                type="primary" if not st.session_state.get("learned_signature") else "secondary",
                disabled=not can_learn,
                use_container_width=True,
            )

            if learn_btn and can_learn:
                # Save uploaded door to temp file
                door_temp_path = OUTPUT_DIR / f"temp_door_{uploaded_door.name}"
                door_temp_path.write_bytes(uploaded_door.getvalue())

                generator = DoorGenerator(api_key=api_key)

                with st.spinner("Learning door style..."):
                    result = generator.learn_door_style(
                        door_temp_path,
                        aspect_ratio=selected_aspect_ratio,
                        door_style_name=door_name,
                        remove_bg=remove_bg,
                    )

                door_temp_path.unlink(missing_ok=True)

                if result.error:
                    st.error(f"Failed: {result.error}")
                elif result.thought_signature:
                    st.session_state.learned_signature = result.thought_signature
                    st.session_state.learned_aspect_ratio = result.aspect_ratio
                    st.session_state.base_door_image = result.image_data
                    st.session_state.door_name = door_name
                    # Clear old results when learning new door
                    st.session_state.generation_results = []
                    st.session_state.generation_errors = []
                    st.success(f"Door style learned! (aspect ratio: {result.aspect_ratio})")
                    st.rerun()

            # Show status
            if st.session_state.get("learned_signature"):
                st.success("Door style ready for variations")

        # Step 2: Select Wood Types
        st.header("2. Select Wood Types")

        swatch_files = get_swatch_files()

        if not swatch_files:
            st.warning(f"No swatches found. Add wood swatch images to the `{SWATCHES_DIR}` folder.")
            st.info("Supported formats: JPG, PNG, WEBP")
        else:
            # Select all / clear buttons
            btn_col1, btn_col2 = st.columns(2)
            if btn_col1.button("Select All", use_container_width=True):
                st.session_state.selected_swatches = [str(f) for f in swatch_files]
            if btn_col2.button("Clear", use_container_width=True):
                st.session_state.selected_swatches = []

            if "selected_swatches" not in st.session_state:
                st.session_state.selected_swatches = []

            # Display swatches in a grid
            st.markdown("**Available Wood Types:**")
            cols_per_row = 3
            for i in range(0, len(swatch_files), cols_per_row):
                cols = st.columns(cols_per_row)
                for j, col in enumerate(cols):
                    idx = i + j
                    if idx < len(swatch_files):
                        swatch = swatch_files[idx]
                        swatch_key = str(swatch)
                        with col:
                            img = Image.open(swatch)
                            st.image(img, use_container_width=True)
                            selected = st.checkbox(
                                swatch_name_from_path(swatch),
                                value=swatch_key in st.session_state.selected_swatches,
                                key=f"swatch_{idx}",
                            )
                            if selected and swatch_key not in st.session_state.selected_swatches:
                                st.session_state.selected_swatches.append(swatch_key)
                            elif not selected and swatch_key in st.session_state.selected_swatches:
                                st.session_state.selected_swatches.remove(swatch_key)

            selected_count = len(st.session_state.selected_swatches)
            st.markdown(f"**Selected: {selected_count} / {len(swatch_files)}**")

    with col_right:
        st.header("3. Generate Variations")

        # Check if ready to generate
        has_signature = st.session_state.get("learned_signature") is not None
        has_swatches = bool(st.session_state.get("selected_swatches"))
        can_generate = api_key and has_signature and has_swatches

        if not api_key:
            st.info("Enter your API key in the sidebar")
        elif not has_signature:
            st.info("Learn a door style first (Step 1)")
        elif not has_swatches:
            st.info("Select at least one wood type (Step 2)")

        generate_btn = st.button(
            "Generate Variations",
            type="primary",
            disabled=not can_generate,
            use_container_width=True,
        )

        if generate_btn and can_generate:
            generator = DoorGenerator(api_key=api_key)
            base_signature = st.session_state.learned_signature
            aspect_ratio = st.session_state.get("learned_aspect_ratio", "3:4")
            wood_types = load_wood_types()

            selected_swatches = [
                (Path(p), swatch_name_from_path(Path(p)))
                for p in st.session_state.selected_swatches
            ]

            progress_bar = st.progress(0)
            status_text = st.empty()
            total = len(selected_swatches)

            successful: list[tuple[str, bytes]] = []
            failed: list[tuple[str, str]] = []

            for i, (swatch_path, wood_name) in enumerate(selected_swatches):
                progress_bar.progress((i) / total)
                status_text.text(f"Generating: {wood_name} ({i + 1}/{total})")

                wood_description = get_wood_description(swatch_path, wood_types)
                result = generator.generate_variation(
                    swatch_image_path=swatch_path,
                    wood_name=wood_name,
                    base_signature=base_signature,
                    aspect_ratio=aspect_ratio,
                    wood_description=wood_description,
                    remove_bg=remove_bg,
                )

                if result.image_data:
                    successful.append((wood_name, result.image_data))
                else:
                    failed.append((wood_name, result.error or "Unknown error"))

            progress_bar.progress(1.0)
            status_text.text(f"Complete: {len(successful)} succeeded, {len(failed)} failed")

            # Append to existing results (don't replace)
            existing = st.session_state.get("generation_results", [])
            existing_errors = st.session_state.get("generation_errors", [])
            st.session_state.generation_results = existing + successful
            st.session_state.generation_errors = existing_errors + failed

        # Display base door
        if st.session_state.get("base_door_image"):
            st.subheader("Base Door (Learned Style)")
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.image(
                    st.session_state.base_door_image,
                    caption="Gemini's interpretation - all variations use this",
                    use_container_width=True,
                )
            st.divider()

        # Display results
        results = st.session_state.get("generation_results", [])
        door_name = st.session_state.get("door_name", "door")

        if results:
            st.subheader(f"Wood Variations ({len(results)})")

            # Download all button
            if len(results) > 1:
                zip_data = create_zip(results, door_name)
                st.download_button(
                    "Download All as ZIP",
                    data=zip_data,
                    file_name=f"{door_name}_variations.zip",
                    mime="application/zip",
                    use_container_width=True,
                )

            # Display grid
            cols_per_row = 3
            for i in range(0, len(results), cols_per_row):
                cols = st.columns(cols_per_row)
                for j, col in enumerate(cols):
                    idx = i + j
                    if idx < len(results):
                        wood_name, image_data = results[idx]
                        with col:
                            st.image(image_data, caption=wood_name, use_container_width=True)
                            filename = f"{door_name}_{wood_name.lower().replace(' ', '_')}.png"
                            st.download_button(
                                "Download",
                                data=image_data,
                                file_name=filename,
                                mime="image/png",
                                key=f"download_{idx}",
                                use_container_width=True,
                            )

        # Display errors
        if st.session_state.get("generation_errors"):
            with st.expander("Errors", expanded=False):
                for wood_name, error in st.session_state.generation_errors:
                    st.error(f"**{wood_name}**: {error}")


if __name__ == "__main__":
    main()
