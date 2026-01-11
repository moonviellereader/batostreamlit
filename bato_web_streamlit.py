#!/usr/bin/env python3
"""
Bato Manga Downloader - WEB VERSION v2.1
Features:
- Bulk Download (Multiple URLs!)
- Stitching Modes (Skip/Short/Normal/Tall/Custom)
- Lossless Quality (300 DPI, no compression)
- Download 1 by 1 with progress tracking
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
import zipfile

# ============ CONFIGURATION ============
st.set_page_config(
    page_title="Bato Manga Downloader v2.1",
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
    """Convert images to PDF with LOSSLESS quality"""
    image_files = []
    for fname in os.listdir(image_folder):
        if fname.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
            image_files.append(os.path.join(image_folder, fname))
    
    image_files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
    
    if not image_files:
        return False
    
    total_images = len(image_files)
    
    # SKIP MODE
    if chunk_height == 0:
        if progress_bar:
            progress_bar.progress(10, text=f"🚀 Skip mode: {total_images} images...")
        
        batch_size = 50
        all_pdf_images = []
        
        for batch_start in range(0, len(image_files), batch_size):
            batch_end = min(batch_start + batch_size, len(image_files))
            batch_files = image_files[batch_start:batch_end]
            
            if progress_bar:
                progress = int(10 + 80 * batch_end / len(image_files))
                progress_bar.progress(progress, text=f"Converting {batch_start+1}-{batch_end}/{len(image_files)}...")
            
            for img_path in batch_files:
                try:
                    img = Image.open(img_path)
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
            progress_bar.progress(95, text=f"Saving ({len(all_pdf_images)} pages)...")
        
        try:
            first_image = all_pdf_images[0]
            other_images = all_pdf_images[1:] if len(all_pdf_images) > 1 else []
            first_image.save(output_pdf_path, 'PDF', resolution=300.0, save_all=True, 
                           append_images=other_images, quality=100, optimize=False, compress_level=0)
            if progress_bar:
                progress_bar.progress(100, text="✅ Complete!")
            return True
        except:
            return False
    
    # STITCHING MODE
    else:
        if progress_bar:
            progress_bar.progress(10, text="Loading images...")
        
        images = []
        min_width = None
        
        for idx, img_path in enumerate(image_files):
            if progress_bar and idx % 10 == 0:
                progress = int(10 + 40 * (idx + 1) / total_images)
                progress_bar.progress(progress, text=f"Loading {idx+1}/{total_images}...")
            
            try:
                img = Image.open(img_path)
                if min_width is None or img.width < min_width:
                    min_width = img.width
                
                if img.mode in ('RGBA', 'LA', 'P'):
                    rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    rgb_img.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = rgb_img
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                if min_width and img.width != min_width:
                    ratio = min_width / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize((min_width, new_height), Image.Resampling.LANCZOS)
                
                images.append(img)
            except:
                continue
        
        if not images:
            return False
        
        if progress_bar:
            progress_bar.progress(55, text="Creating chunks...")
        
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
        
        if progress_bar:
            progress_bar.progress(60, text=f"Stitching {len(chunks)} chunks...")
        
        stitched_images = []
        for chunk_idx, chunk in enumerate(chunks):
            if progress_bar:
                progress = int(60 + 30 * (chunk_idx + 1) / len(chunks))
                progress_bar.progress(progress, text=f"Stitching {chunk_idx+1}/{len(chunks)}...")
            
            chunk_height_px = sum(img.height for img in chunk)
            stitched = Image.new('RGB', (min_width, chunk_height_px), (255, 255, 255))
            
            y_offset = 0
            for img in chunk:
                stitched.paste(img, (0, y_offset))
                y_offset += img.height
            
            stitched_images.append(stitched)
        
        if progress_bar:
            progress_bar.progress(95, text=f"Saving ({len(stitched_images)} pages)...")
        
        if stitched_images:
            try:
                first_image = stitched_images[0]
                other_images = stitched_images[1:] if len(stitched_images) > 1 else []
                first_image.save(output_pdf_path, 'PDF', resolution=300.0, save_all=True, 
                               append_images=other_images, quality=100, optimize=False, compress_level=0)
                if progress_bar:
                    progress_bar.progress(100, text="✅ Complete!")
                return True
            except:
                return False
        
        return False

def parse_urls(text):
    """Parse multiple URLs from text"""
    lines = text.strip().split('\n')
    urls = []
    for line in lines:
        line = line.strip()
        if line and any(domain in line for domain in BATO_DOMAINS):
            urls.append(line)
    return urls

# ============ STREAMLIT UI ============

def main():
    # Initialize session state
    if 'downloads' not in st.session_state:
        st.session_state.downloads = 0
    if 'stitch_mode' not in st.session_state:
        st.session_state.stitch_mode = 'skip'
    if 'custom_height' not in st.session_state:
        st.session_state.custom_height = 10000
    if 'download_mode' not in st.session_state:
        st.session_state.download_mode = 'single'
    
    # Header
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("📚 Bato Manga Downloader")
        st.markdown("### v2.1 - Bulk Download + Stitching + Lossless")
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        st.success("✨ LOSSLESS")
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Settings")
        
        st.success("✨ **Lossless Quality**")
        st.caption("300 DPI • No compression")
        
        st.divider()
        
        # Download mode selector
        st.subheader("📦 Download Mode")
        download_mode = st.radio(
            "Select mode:",
            options=['single', 'bulk'],
            format_func=lambda x: '📄 Single URL' if x == 'single' else '📦 Bulk Download',
            key='download_mode_selector'
        )
        st.session_state.download_mode = download_mode
        
        if download_mode == 'bulk':
            st.info("💡 Paste multiple URLs (1 per line). Download 1 by 1 sequentially.")
        
        st.divider()
        
        # Stitching mode
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
        st.info(STITCH_PRESETS[selected_mode]['desc'])
        
        if selected_mode == 'custom':
            custom_height = st.slider(
                "Chunk Height (px):",
                min_value=1000,
                max_value=50000,
                value=st.session_state.custom_height,
                step=1000
            )
            st.session_state.custom_height = custom_height
            chunk_height = custom_height
            st.caption(f"📏 {chunk_height:,}px")
        else:
            chunk_height = STITCH_PRESETS[selected_mode]['height']
        
        st.divider()
        
        # Current settings
        st.markdown("**📊 Current:**")
        if chunk_height == 0:
            st.metric("Mode", "🚀 Skip")
        else:
            st.metric("Mode", f"{chunk_height:,}px")
        st.metric("Quality", "✨ 300 DPI")
        
        st.divider()
        
        # Info
        with st.expander("ℹ️ Info"):
            st.write("""
            **v2.1 Features:**
            - ✅ Bulk download (NEW!)
            - ✅ Custom stitching
            - ✅ Lossless quality
            - ✅ 300 DPI output
            - ✅ ZIP packaging
            """)
        
        with st.expander("📖 Bulk Guide"):
            st.markdown("""
            **How to use:**
            1. Select "Bulk Download"
            2. Paste URLs (1 per line)
            3. Click "Download All"
            4. Wait for processing
            5. Get ZIP file!
            
            **Features:**
            - Download 1 by 1
            - Progress tracking
            - Auto ZIP packaging
            - Failed URLs skipped
            """)
        
        st.divider()
        st.metric("Total Downloads", st.session_state.downloads)
        st.caption("@moonread_channel")
    
    # Main area
    st.markdown("---")
    
    # Download mode UI
    if st.session_state.download_mode == 'single':
        # SINGLE MODE
        col1, col2 = st.columns([3, 1])
        
        with col1:
            chapter_url = st.text_input(
                "📎 Paste Bato Chapter URL:",
                placeholder="https://bato.ing/chapter/123456"
            )
        
        with col2:
            st.write("")
            st.write("")
            download_button = st.button("⬇️ Download", type="primary", use_container_width=True)
        
        # Process single download
        if download_button and chapter_url:
            process_single_download(chapter_url, chunk_height)
    
    else:
        # BULK MODE
        st.subheader("📦 Bulk Download Mode")
        
        urls_text = st.text_area(
            "📎 Paste Chapter URLs (1 per line):",
            placeholder="https://bato.ing/chapter/123456\nhttps://bato.ing/chapter/123457\nhttps://bato.ing/chapter/123458",
            height=200
        )
        
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col2:
            download_all_button = st.button("📦 Download All", type="primary", use_container_width=True)
        
        # Process bulk download
        if download_all_button and urls_text:
            urls = parse_urls(urls_text)
            
            if not urls:
                st.error("❌ No valid Bato URLs found!")
                return
            
            st.success(f"✅ Found {len(urls)} URLs to download")
            
            process_bulk_download(urls, chunk_height)
    
    # Mode banner
    if chunk_height == 0:
        st.info("🚀 Skip Mode | Lossless 300 DPI")
    elif chunk_height <= 15000:
        st.info(f"📄 {chunk_height:,}px chunks | Lossless 300 DPI")
    else:
        st.warning(f"📏 {chunk_height:,}px chunks | Lossless 300 DPI")
    
    # Examples
    with st.expander("📝 Example URLs"):
        if st.session_state.download_mode == 'single':
            st.code("https://bato.si/chapter/123456")
        else:
            st.code("""https://bato.si/chapter/123456
https://bato.si/chapter/123457
https://bato.si/chapter/123458""")
    
    # Footer
    st.write("---")
    st.markdown("""
    <div style='text-align: center; color: gray;'>
    <p>v2.1 - Bulk Download • Lossless Quality • @moonread_channel</p>
    </div>
    """, unsafe_allow_html=True)

def process_single_download(chapter_url, chunk_height):
    """Process single chapter download"""
    is_bato_url = any(domain in chapter_url for domain in BATO_DOMAINS)
    
    if not is_bato_url:
        st.error("❌ Not a valid Bato URL!")
        return
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        with st.spinner("🔍 Fetching chapter..."):
            chapter_info = get_chapter_info(chapter_url)
        
        if not chapter_info:
            st.error("❌ Failed to fetch chapter!")
            return
        
        total_images = len(chapter_info['images'])
        chapter_title = sanitize_filename(chapter_info['title'])
        
        st.success(f"✅ {chapter_info['title']} ({total_images} images)")
        
        if total_images >= 100 and chunk_height > 0:
            st.warning(f"💡 {total_images} images! Consider Skip mode.")
        
        st.write("---")
        st.subheader("📥 Downloading")
        
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
                        download_status.write(f"{downloaded}/{total_images} ({percent}%)")
        
        if downloaded == 0:
            st.error("❌ Failed to download images!")
            return
        
        st.success(f"✅ Downloaded {downloaded} images")
        
        st.write("---")
        st.subheader("📄 Creating PDF")
        
        pdf_progress = st.progress(0)
        pdf_path = os.path.join(temp_dir, f"{chapter_title}.pdf")
        
        success = images_to_pdf_lossless(temp_folder, pdf_path, chunk_height, pdf_progress)
        
        if not success:
            st.error("❌ PDF creation failed!")
            return
        
        total_time = time.time() - start_time
        file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
        
        st.success(f"✅ PDF created ({file_size_mb:.1f}MB in {total_time:.1f}s)")
        
        st.write("---")
        
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
        
        st.session_state.downloads += 1
        
        st.info(f"**Chapter:** {chapter_info['title']} | **Size:** {file_size_mb:.1f}MB | **Time:** {total_time:.1f}s")
        
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
    finally:
        try:
            shutil.rmtree(temp_dir)
        except:
            pass

def process_bulk_download(urls, chunk_height):
    """Process bulk download - download 1 by 1"""
    temp_dir = tempfile.mkdtemp()
    pdf_files = []
    
    try:
        st.write("---")
        st.subheader(f"📦 Processing {len(urls)} Chapters")
        
        # Overall progress
        overall_progress = st.progress(0)
        overall_status = st.empty()
        
        start_time = time.time()
        
        for idx, url in enumerate(urls, 1):
            overall_status.write(f"**Processing Chapter {idx}/{len(urls)}**")
            
            # Chapter section
            with st.expander(f"📄 Chapter {idx}/{len(urls)}", expanded=True):
                st.write(f"URL: `{url[:50]}...`")
                
                try:
                    # Fetch chapter
                    with st.spinner("Fetching..."):
                        chapter_info = get_chapter_info(url)
                    
                    if not chapter_info:
                        st.error(f"❌ Failed to fetch chapter {idx}")
                        continue
                    
                    total_images = len(chapter_info['images'])
                    chapter_title = sanitize_filename(chapter_info['title'])
                    
                    st.success(f"✅ {chapter_info['title']} ({total_images} images)")
                    
                    # Download images
                    download_progress = st.progress(0)
                    download_status = st.empty()
                    
                    temp_folder = os.path.join(temp_dir, f"chapter_{idx}_{chapter_title}")
                    os.makedirs(temp_folder, exist_ok=True)
                    
                    downloaded = 0
                    
                    with ThreadPoolExecutor(max_workers=6) as executor:
                        futures = []
                        for img_idx, img_url in enumerate(chapter_info['images'], 1):
                            save_path = os.path.join(temp_folder, f"page_{img_idx:04d}.jpg")
                            future = executor.submit(download_image, img_url, save_path)
                            futures.append(future)
                        
                        for future in futures:
                            if future.result():
                                downloaded += 1
                                percent = int(100 * downloaded / total_images)
                                if downloaded % 5 == 0 or downloaded == total_images:
                                    download_progress.progress(percent / 100)
                                    download_status.write(f"Downloaded: {downloaded}/{total_images}")
                    
                    if downloaded == 0:
                        st.error(f"❌ No images downloaded for chapter {idx}")
                        continue
                    
                    # Create PDF
                    pdf_progress = st.progress(0)
                    pdf_path = os.path.join(temp_dir, f"{chapter_title}.pdf")
                    
                    success = images_to_pdf_lossless(temp_folder, pdf_path, chunk_height, pdf_progress)
                    
                    if success:
                        file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
                        st.success(f"✅ PDF created ({file_size_mb:.1f}MB)")
                        pdf_files.append((pdf_path, chapter_title))
                    else:
                        st.error(f"❌ PDF creation failed for chapter {idx}")
                    
                except Exception as e:
                    st.error(f"❌ Error on chapter {idx}: {str(e)}")
                    continue
            
            # Update overall progress
            overall_progress.progress(idx / len(urls))
        
        # Create ZIP if we have PDFs
        if pdf_files:
            st.write("---")
            st.subheader("📦 Packaging")
            
            with st.spinner("Creating ZIP file..."):
                zip_path = os.path.join(temp_dir, "Bato_Bulk_Download.zip")
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for pdf_path, title in pdf_files:
                        zipf.write(pdf_path, f"{title}.pdf")
            
            zip_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
            total_time = time.time() - start_time
            
            st.success(f"✅ Created ZIP with {len(pdf_files)} PDFs ({zip_size_mb:.1f}MB in {total_time:.1f}s)")
            
            st.write("---")
            
            with open(zip_path, 'rb') as f:
                zip_data = f.read()
            
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.download_button(
                    label=f"📦 Download ZIP ({len(pdf_files)} PDFs, {zip_size_mb:.1f}MB)",
                    data=zip_data,
                    file_name="Bato_Bulk_Download.zip",
                    mime="application/zip",
                    use_container_width=True
                )
            
            st.session_state.downloads += len(pdf_files)
            
            st.info(f"""
            **Summary:**
            - Successfully downloaded: {len(pdf_files)}/{len(urls)} chapters
            - Total size: {zip_size_mb:.1f}MB
            - Total time: {total_time:.1f}s
            """)
        else:
            st.error("❌ No PDFs were created successfully!")
        
    except Exception as e:
        st.error(f"❌ Bulk download error: {str(e)}")
    finally:
        try:
            shutil.rmtree(temp_dir)
        except:
            pass

if __name__ == "__main__":
    main()
