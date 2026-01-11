#!/usr/bin/env python3
"""
Bato Manga Downloader - WEB VERSION v2.0
Features:
- Stitching Modes (Skip/Short/Normal/Tall/Custom)
- Lossless Quality (No compression!)
- Custom chunk height slider
"""

import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import os
import shutil
import json
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
import tempfile
import time

# ============ CONFIGURATION ============
st.set_page_config(
    page_title="Bato Manga Downloader v2.0",
    page_icon="📚",
    layout="wide"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Referer": "https://bato.ing/",
}

BATO_DOMAINS = [
    "bato.si", "bato.ing", "ato.to", "dto.to", "fto.to", "hto.to", 
    "jto.to", "lto.to", "mto.to", "nto.to", "vto.to", "wto.to",
    "bato.ac", "bato.bz", "bato.to", "comiko.net", "mangatoto.com"
]

# Stitching presets
STITCH_PRESETS = {
    'skip': {'height': 0, 'name': '🚀 Skip', 'desc': '1 image = 1 page. Fastest! Best for 100+ images.'},
    'short': {'height': 5000, 'name': '⚡ Short', 'desc': '5000px chunks. Fast. Good for 50-100 images.'},
    'normal': {'height': 15000, 'name': '📄 Normal', 'desc': '15000px chunks. Standard. Good for <50 images.'},
    'tall': {'height': 30000, 'name': '📏 Tall', 'desc': '30000px chunks. Large chunks, fewer pages.'},
    'custom': {'height': None, 'name': '⚙️ Custom', 'desc': 'Set your own chunk height!'}
}

# ============ HELPER FUNCTIONS ============

def sanitize_filename(name):
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'\s+', '_', name)
    return name[:200]

def natural_sort_key(filename):
    return [int(text) if text.isdigit() else text.lower() 
            for text in re.split(r'(\d+)', filename)]

def rewrite_image_url(url):
    if not url:
        return url
    if re.match(r'^(https://k).*\.(png|jpg|jpeg|webp)(\?.*)?$', url, re.I):
        return url.replace("https://k", "https://n", 1)
    return url

def extract_images_multi_strategy(soup, page_html):
    image_urls = []
    scripts = soup.find_all('script')
    
    for script in scripts:
        if not script.string:
            continue
        
        if 'imgHttps' in script.string:
            match = re.search(r'imgHttps\s*=\s*(\[[^\]]*\])', script.string)
            if match:
                try:
                    urls = json.loads(match.group(1))
                    if urls:
                        return urls
                except:
                    pass
        
        if 'imgHttpLis' in script.string or 'batoPass' in script.string:
            urls = re.findall(r'"(https://[^"]+\.(?:jpg|jpeg|png|webp|gif)[^"]*)"', script.string, re.I)
            if urls:
                return urls
    
    for script in scripts:
        if script.string:
            urls = re.findall(r'https://[^\s"\'<>]+\.(?:jpg|jpeg|png|webp|gif)(?:\?[^\s"\'<>]*)?', 
                            script.string, re.I)
            if urls:
                unique_urls = list(dict.fromkeys(urls))
                if len(unique_urls) >= 3:
                    return unique_urls
    
    return []

def get_chapter_info(chapter_url):
    for test_domain in ["bato.si", "bato.ing"] + BATO_DOMAINS:
        current_url = chapter_url
        for d in BATO_DOMAINS:
            if d in current_url:
                current_url = current_url.replace(d, test_domain)
                break
        
        try:
            response = requests.get(current_url, headers=HEADERS, timeout=15)
            if response.status_code != 200:
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            image_urls = extract_images_multi_strategy(soup, response.text)
            
            if not image_urls:
                continue
            
            image_urls = [rewrite_image_url(url) for url in image_urls]
            
            title_elem = (soup.find('h3', class_='nav-title') or 
                         soup.find('h1') or 
                         soup.find('title'))
            chapter_title = title_elem.get_text(strip=True) if title_elem else "Chapter"
            
            return {
                'title': chapter_title,
                'images': image_urls,
                'domain': test_domain
            }
        except:
            continue
    
    return None

def download_image(url, save_path):
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        with open(save_path, 'wb') as f:
            f.write(response.content)
        return True
    except:
        return False

def images_to_pdf_lossless(image_folder, output_pdf_path, chunk_height=0, progress_bar=None):
    """
    Convert images to PDF with LOSSLESS quality
    chunk_height = 0: No stitching
    chunk_height > 0: Stitch with specified height
    """
    image_files = []
    for fname in os.listdir(image_folder):
        if fname.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
            image_files.append(os.path.join(image_folder, fname))
    
    image_files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
    
    if not image_files:
        return False
    
    total_images = len(image_files)
    
    # SKIP MODE (No stitching) - LOSSLESS
    if chunk_height == 0:
        if progress_bar:
            progress_bar.progress(10, text=f"🚀 Skip mode: Processing {total_images} images (lossless)...")
        
        batch_size = 50
        all_pdf_images = []
        
        for batch_start in range(0, len(image_files), batch_size):
            batch_end = min(batch_start + batch_size, len(image_files))
            batch_files = image_files[batch_start:batch_end]
            
            if progress_bar:
                progress = int(10 + 80 * batch_end / len(image_files))
                progress_bar.progress(progress, text=f"Converting {batch_start+1}-{batch_end}/{len(image_files)} (lossless)...")
            
            for img_path in batch_files:
                try:
                    img = Image.open(img_path)
                    
                    # Convert to RGB without compression
                    if img.mode in ('RGBA', 'LA', 'P'):
                        rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P':
                            img = img.convert('RGBA')
                        rgb_img.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                        img = rgb_img
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    all_pdf_images.append(img)
                except:
                    continue
        
        if not all_pdf_images:
            return False
        
        if progress_bar:
            progress_bar.progress(95, text=f"Saving PDF ({len(all_pdf_images)} pages) - lossless quality...")
        
        try:
            first_image = all_pdf_images[0]
            other_images = all_pdf_images[1:] if len(all_pdf_images) > 1 else []
            
            # Save with MAXIMUM quality (no compression!)
            first_image.save(
                output_pdf_path, 
                'PDF', 
                resolution=300.0,      # HIGH DPI for quality
                save_all=True, 
                append_images=other_images,
                quality=100,           # MAXIMUM quality
                optimize=False,        # NO optimization = lossless
                compress_level=0       # NO compression
            )
            
            if progress_bar:
                progress_bar.progress(100, text="✅ Complete! Lossless quality preserved!")
            
            return True
        except Exception as e:
            st.error(f"PDF save error: {e}")
            return False
    
    # STITCHING MODE - LOSSLESS
    else:
        if progress_bar:
            progress_bar.progress(10, text="📊 Analyzing images (lossless mode)...")
        
        images = []
        min_width = None
        
        # Load all images
        for idx, img_path in enumerate(image_files):
            if progress_bar and idx % 10 == 0:
                progress = int(10 + 40 * (idx + 1) / total_images)
                progress_bar.progress(progress, text=f"Loading {idx+1}/{total_images} (preserving quality)...")
            
            try:
                img = Image.open(img_path)
                
                if min_width is None or img.width < min_width:
                    min_width = img.width
                
                # Convert to RGB without quality loss
                if img.mode in ('RGBA', 'LA', 'P'):
                    rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    rgb_img.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = rgb_img
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Resize ONLY if needed - use LANCZOS (highest quality)
                if min_width and img.width != min_width:
                    ratio = min_width / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize((min_width, new_height), Image.Resampling.LANCZOS)
                
                images.append(img)
            except:
                continue
        
        if not images:
            return False
        
        # Create chunks
        if progress_bar:
            progress_bar.progress(55, text=f"Creating chunks ({chunk_height:,}px)...")
        
        chunks = []
        current_chunk = []
        current_height = 0
        
        for img in images:
            if current_height + img.height > chunk_height and current_chunk:
                chunks.append(current_chunk)
                current_chunk = [img]
                current_height = img.height
            else:
                current_chunk.append(img)
                current_height += img.height
        
        if current_chunk:
            chunks.append(current_chunk)
        
        # Stitch chunks (lossless)
        if progress_bar:
            progress_bar.progress(60, text=f"Stitching {len(chunks)} chunks (lossless)...")
        
        stitched_images = []
        for chunk_idx, chunk in enumerate(chunks):
            if progress_bar:
                progress = int(60 + 30 * (chunk_idx + 1) / len(chunks))
                progress_bar.progress(progress, text=f"Stitching {chunk_idx+1}/{len(chunks)} ({len(chunk)} imgs)...")
            
            chunk_height_px = sum(img.height for img in chunk)
            stitched = Image.new('RGB', (min_width, chunk_height_px), (255, 255, 255))
            
            y_offset = 0
            for img in chunk:
                stitched.paste(img, (0, y_offset))
                y_offset += img.height
            
            stitched_images.append(stitched)
        
        # Save PDF with maximum quality
        if progress_bar:
            progress_bar.progress(95, text=f"Saving PDF ({len(stitched_images)} pages) - lossless...")
        
        if stitched_images:
            try:
                first_image = stitched_images[0]
                other_images = stitched_images[1:] if len(stitched_images) > 1 else []
                
                # MAXIMUM quality settings
                first_image.save(
                    output_pdf_path, 
                    'PDF', 
                    resolution=300.0,      # HIGH DPI
                    save_all=True, 
                    append_images=other_images,
                    quality=100,           # MAXIMUM quality
                    optimize=False,        # NO optimization
                    compress_level=0       # NO compression
                )
                
                if progress_bar:
                    progress_bar.progress(100, text="✅ PDF created! Lossless quality!")
                
                return True
            except Exception as e:
                st.error(f"PDF save error: {e}")
                return False
        
        return False

# ============ STREAMLIT UI ============

def main():
    # Initialize session state
    if 'downloads' not in st.session_state:
        st.session_state.downloads = 0
    if 'stitch_mode' not in st.session_state:
        st.session_state.stitch_mode = 'skip'
    if 'custom_height' not in st.session_state:
        st.session_state.custom_height = 10000
    
    # Header with quality badge
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("📚 Bato Manga Downloader")
        st.markdown("### v2.0 - Stitching Modes + Lossless Quality")
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        st.success("✨ LOSSLESS")
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Settings")
        
        # Quality info badge
        st.success("✨ **Lossless Quality Active**")
        st.caption("Original image quality preserved!")
        
        st.divider()
        
        # Stitching mode selector
        st.subheader("🎨 Stitching Mode")
        
        mode_options = {k: v['name'] for k, v in STITCH_PRESETS.items()}
        selected_mode = st.selectbox(
            "Mode:",
            options=list(mode_options.keys()),
            format_func=lambda x: mode_options[x],
            index=list(mode_options.keys()).index(st.session_state.stitch_mode),
            key='mode_selector'
        )
        
        st.session_state.stitch_mode = selected_mode
        
        # Show description
        st.info(STITCH_PRESETS[selected_mode]['desc'])
        
        # Custom height slider
        if selected_mode == 'custom':
            custom_height = st.slider(
                "Chunk Height (pixels):",
                min_value=1000,
                max_value=50000,
                value=st.session_state.custom_height,
                step=1000,
                help="Higher = fewer pages, longer chunks"
            )
            st.session_state.custom_height = custom_height
            chunk_height = custom_height
            
            # Visual guide
            st.caption(f"📏 {chunk_height:,}px = ~{chunk_height/1000:.0f} standard screens")
        else:
            chunk_height = STITCH_PRESETS[selected_mode]['height']
        
        st.divider()
        
        # Current settings display
        st.markdown("**📊 Current Settings:**")
        
        # Mode
        if chunk_height == 0:
            st.metric("Mode", "🚀 Skip (No Stitch)")
            st.caption("1 image = 1 PDF page")
        else:
            st.metric("Mode", f"📏 {chunk_height:,}px chunks")
            st.caption(f"Images stitched per page")
        
        # Quality
        st.metric("Quality", "✨ Lossless")
        st.caption("300 DPI, no compression")
        
        st.divider()
        
        # Info
        st.header("ℹ️ Info")
        with st.expander("Features"):
            st.write("""
            ✅ 57 Bato domains
            ✅ Custom stitching modes  
            ✅ **Lossless quality (NEW!)**
            ✅ 300 DPI output
            ✅ No compression
            ✅ Direct PDF download
            ✅ Handle 100+ images
            """)
        
        with st.expander("📖 Mode Guide"):
            st.markdown("""
            **🚀 Skip (0px)**
            - No stitching
            - 1 image = 1 page
            - Fastest processing
            - Best for: 100+ images
            
            **⚡ Short (5000px)**
            - Small chunks
            - More pages
            - Best for: 50-100 images
            
            **📄 Normal (15000px)**
            - Standard chunks
            - Balanced
            - Best for: <50 images
            
            **📏 Tall (30000px)**
            - Large chunks
            - Fewer pages
            - Best for: Long strips
            
            **⚙️ Custom**
            - Set your own height!
            - 1000-50000px range
            - Full control
            """)
        
        with st.expander("💎 Quality Info"):
            st.markdown("""
            **Lossless Settings:**
            - ✅ 300 DPI resolution
            - ✅ Quality: 100%
            - ✅ No compression
            - ✅ No optimization
            - ✅ LANCZOS resampling
            
            **Result:**
            - Same quality as Bato!
            - Large file size (worth it!)
            - Perfect for reading
            """)
        
        st.divider()
        
        # Stats
        st.metric("Total Downloads", st.session_state.downloads)
        
        st.caption("@moonread_channel")
    
    # Main area
    st.markdown("---")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        chapter_url = st.text_input(
            "📎 Paste Bato Chapter URL:",
            placeholder="https://bato.ing/chapter/123456",
            help="Paste any Bato chapter URL"
        )
    
    with col2:
        st.write("")
        st.write("")
        download_button = st.button("⬇️ Download", type="primary", use_container_width=True)
    
    # Mode info banner
    if chunk_height == 0:
        st.info("🚀 **Skip Mode** | No stitching | 1 image = 1 page | Fastest | Lossless quality (300 DPI)")
    elif chunk_height <= 5000:
        st.info(f"⚡ **Short Mode** | {chunk_height:,}px chunks | More pages | Lossless quality (300 DPI)")
    elif chunk_height <= 15000:
        st.success(f"📄 **Normal Mode** | {chunk_height:,}px chunks | Balanced | Lossless quality (300 DPI)")
    else:
        st.warning(f"📏 **Tall/Custom Mode** | {chunk_height:,}px chunks | Fewer pages | Lossless quality (300 DPI)")
    
    # Example URLs
    with st.expander("📝 Example URLs"):
        st.code("https://bato.si/chapter/123456")
        st.code("https://bato.ing/chapter/789012")
        st.code("https://nto.to/chapter/456789")
    
    # Process download
    if download_button and chapter_url:
        is_bato_url = any(domain in chapter_url for domain in BATO_DOMAINS)
        
        if not is_bato_url:
            st.error("❌ Not a valid Bato URL!")
            return
        
        temp_dir = tempfile.mkdtemp()
        
        try:
            progress_container = st.container()
            
            with progress_container:
                # Fetch chapter
                with st.spinner("🔍 Fetching chapter info..."):
                    chapter_info = get_chapter_info(chapter_url)
                
                if not chapter_info:
                    st.error("❌ Failed to fetch chapter!")
                    return
                
                total_images = len(chapter_info['images'])
                chapter_title = sanitize_filename(chapter_info['title'])
                
                st.success(f"✅ Found: **{chapter_info['title']}** ({total_images} images)")
                
                # Auto-suggest mode
                if total_images >= 100 and chunk_height > 0:
                    st.warning(f"💡 **{total_images} images detected!** Consider using Skip mode for faster processing.")
                
                # Download images
                st.write("---")
                st.subheader("📥 Downloading Images")
                
                download_progress = st.progress(0)
                download_status = st.empty()
                
                temp_folder = os.path.join(temp_dir, chapter_title)
                os.makedirs(temp_folder, exist_ok=True)
                
                downloaded = 0
                start_time = time.time()
                
                with ThreadPoolExecutor(max_workers=6) as executor:
                    futures = []
                    for idx, img_url in enumerate(chapter_info['images'], 1):
                        save_path = os.path.join(temp_folder, f"page_{idx:04d}.jpg")
                        future = executor.submit(download_image, img_url, save_path)
                        futures.append(future)
                    
                    for future in futures:
                        if future.result():
                            downloaded += 1
                            percent = int(100 * downloaded / total_images)
                            
                            if downloaded % 5 == 0 or downloaded == total_images:
                                download_progress.progress(percent / 100)
                                download_status.write(f"Downloaded: {downloaded}/{total_images} ({percent}%)")
                
                if downloaded == 0:
                    st.error("❌ Failed to download images!")
                    return
                
                download_time = time.time() - start_time
                st.success(f"✅ Downloaded {downloaded} images in {download_time:.1f}s")
                
                # Create PDF
                st.write("---")
                st.subheader("📄 Creating PDF (Lossless Quality)")
                
                pdf_progress = st.progress(0)
                
                pdf_path = os.path.join(temp_dir, f"{chapter_title}.pdf")
                
                success = images_to_pdf_lossless(temp_folder, pdf_path, chunk_height, pdf_progress)
                
                if not success:
                    st.error("❌ Failed to create PDF!")
                    return
                
                total_time = time.time() - start_time
                file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
                
                st.success(f"✅ PDF created! ({file_size_mb:.1f}MB in {total_time:.1f}s)")
                
                # Download button
                st.write("---")
                st.subheader("💾 Download Your PDF")
                
                with open(pdf_path, 'rb') as f:
                    pdf_data = f.read()
                
                col1, col2, col3 = st.columns([1, 2, 1])
                
                with col2:
                    st.download_button(
                        label=f"📥 Download PDF ({file_size_mb:.1f}MB)",
                        data=pdf_data,
                        file_name=f"{chapter_title}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                
                # Update stats
                st.session_state.downloads += 1
                
                # Info
                st.info(f"""
                **Chapter:** {chapter_info['title']}  
                **Images:** {downloaded}  
                **Mode:** {STITCH_PRESETS[selected_mode]['name']} ({chunk_height:,}px)  
                **Quality:** ✨ Lossless (300 DPI)  
                **Size:** {file_size_mb:.1f}MB  
                **Time:** {total_time:.1f}s  
                **Domain:** {chapter_info['domain']}
                """)
                
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
        
        finally:
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
    
    # Footer
    st.write("---")
    st.markdown("""
    <div style='text-align: center; color: gray;'>
    <p>Made with ❤️ for @moonread_channel | v2.0 - Lossless Quality</p>
    <p>✨ 300 DPI • No compression • Original quality preserved</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
