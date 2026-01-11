#!/usr/bin/env python3
"""
Bato Manga Downloader - WEB VERSION (Streamlit)
Better for many users - No bot rate limits!
Deploy: Streamlit Cloud (FREE!) or any server
"""

import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import os
import shutil
import zipfile
import json
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
import tempfile
import time

# ============ CONFIGURATION ============
st.set_page_config(
    page_title="Bato Manga Downloader",
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

# ============ HELPER FUNCTIONS ============

def sanitize_filename(name):
    """Clean filename"""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'\s+', '_', name)
    return name[:200]

def natural_sort_key(filename):
    """Natural sorting"""
    return [int(text) if text.isdigit() else text.lower() 
            for text in re.split(r'(\d+)', filename)]

def rewrite_image_url(url):
    """Rewrite image URL"""
    if not url:
        return url
    if re.match(r'^(https://k).*\.(png|jpg|jpeg|webp)(\?.*)?$', url, re.I):
        return url.replace("https://k", "https://n", 1)
    return url

def find_working_domain():
    """Find working domain"""
    for domain in ["bato.si", "bato.ing"]:
        try:
            url = f"https://{domain}"
            response = requests.get(url, headers=HEADERS, timeout=5)
            if response.status_code == 200:
                return domain
        except:
            continue
    return "bato.si"

def extract_images_multi_strategy(soup, page_html):
    """Extract image URLs"""
    image_urls = []
    
    # STRATEGY 1: imgHttps array
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
    
    # STRATEGY 2: All HTTPS image URLs
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
    """Get chapter info"""
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
    """Download single image"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        with open(save_path, 'wb') as f:
            f.write(response.content)
        return True
    except:
        return False

def images_to_pdf_batch(image_folder, output_pdf_path, progress_bar=None):
    """Convert images to PDF with batch processing"""
    image_files = []
    for fname in os.listdir(image_folder):
        if fname.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
            image_files.append(os.path.join(image_folder, fname))
    
    image_files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
    
    if not image_files:
        return False
    
    # Batch processing for 50+ images
    batch_size = 50
    all_pdf_images = []
    
    for batch_start in range(0, len(image_files), batch_size):
        batch_end = min(batch_start + batch_size, len(image_files))
        batch_files = image_files[batch_start:batch_end]
        
        if progress_bar:
            progress = int(100 * batch_end / len(image_files))
            progress_bar.progress(progress, text=f"Converting batch {batch_start+1}-{batch_end}/{len(image_files)}...")
        
        for img_path in batch_files:
            try:
                img = Image.open(img_path)
                
                # Convert to RGB
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
    
    # Save as PDF
    if progress_bar:
        progress_bar.progress(95, text=f"Finalizing PDF ({len(all_pdf_images)} pages)...")
    
    try:
        first_image = all_pdf_images[0]
        other_images = all_pdf_images[1:] if len(all_pdf_images) > 1 else []
        
        first_image.save(
            output_pdf_path, 
            'PDF', 
            resolution=72.0,
            save_all=True, 
            append_images=other_images,
            optimize=False
        )
        
        if progress_bar:
            progress_bar.progress(100, text="Complete!")
        
        return True
    except Exception as e:
        st.error(f"PDF save error: {e}")
        return False

# ============ STREAMLIT UI ============

def main():
    # Header
    st.title("📚 Bato Manga Downloader")
    st.markdown("### Web Version - Better for Many Users!")
    st.markdown("**No bot limits, no queue, instant download!**")
    
    # Sidebar
    with st.sidebar:
        st.header("ℹ️ Info")
        st.write("""
        **Features:**
        - ✅ 57 Bato domains
        - ✅ Batch processing
        - ✅ Direct PDF download
        - ✅ No rate limits
        - ✅ Handle 100+ images
        
        **Support:**
        - @moonread_channel
        
        **Tips:**
        - Paste chapter URL
        - Click Download
        - Wait for processing
        - Download PDF
        """)
        
        st.divider()
        
        # Stats
        if 'downloads' not in st.session_state:
            st.session_state.downloads = 0
        
        st.metric("Total Downloads", st.session_state.downloads)
    
    # Main area
    col1, col2 = st.columns([3, 1])
    
    with col1:
        chapter_url = st.text_input(
            "📎 Paste Bato Chapter URL:",
            placeholder="https://bato.ing/chapter/123456",
            help="Paste any Bato chapter URL from any domain"
        )
    
    with col2:
        st.write("")  # Spacing
        st.write("")  # Spacing
        download_button = st.button("⬇️ Download PDF", type="primary", use_container_width=True)
    
    # Example URLs
    with st.expander("📝 Example URLs"):
        st.code("https://bato.si/chapter/123456")
        st.code("https://bato.ing/chapter/789012")
        st.code("https://nto.to/chapter/456789")
        st.code("https://comiko.org/title/xxx/chapter-1")
    
    # Process download
    if download_button and chapter_url:
        # Validate URL
        is_bato_url = any(domain in chapter_url for domain in BATO_DOMAINS)
        
        if not is_bato_url:
            st.error("❌ Not a valid Bato URL! Please check the URL.")
            return
        
        # Create temp directory
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Progress
            progress_container = st.container()
            
            with progress_container:
                # Step 1: Fetch chapter info
                with st.spinner("🔍 Fetching chapter info..."):
                    chapter_info = get_chapter_info(chapter_url)
                
                if not chapter_info:
                    st.error("❌ Failed to fetch chapter! URL might be invalid or domain is down.")
                    return
                
                total_images = len(chapter_info['images'])
                chapter_title = sanitize_filename(chapter_info['title'])
                
                st.success(f"✅ Found: **{chapter_info['title']}** ({total_images} images)")
                
                # Recommendation for 100+
                if total_images >= 100:
                    st.info(f"💡 **{total_images} images detected!** Using batch processing for optimal performance.")
                
                # Step 2: Download images
                st.write("---")
                st.subheader("📥 Downloading Images")
                
                download_progress = st.progress(0, text="Starting download...")
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
                                download_progress.progress(percent, text=f"Downloaded {downloaded}/{total_images}...")
                                download_status.write(f"Progress: {downloaded}/{total_images} ({percent}%)")
                
                if downloaded == 0:
                    st.error("❌ Failed to download images!")
                    return
                
                download_time = time.time() - start_time
                st.success(f"✅ Downloaded {downloaded} images in {download_time:.1f}s")
                
                # Step 3: Create PDF
                st.write("---")
                st.subheader("📄 Creating PDF")
                
                pdf_progress = st.progress(0, text="Initializing...")
                
                pdf_path = os.path.join(temp_dir, f"{chapter_title}.pdf")
                
                success = images_to_pdf_batch(temp_folder, pdf_path, pdf_progress)
                
                if not success:
                    st.error("❌ Failed to create PDF!")
                    return
                
                total_time = time.time() - start_time
                file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
                
                st.success(f"✅ PDF created! ({file_size_mb:.1f}MB in {total_time:.1f}s)")
                
                # Step 4: Download button
                st.write("---")
                st.subheader("💾 Download Your PDF")
                
                with open(pdf_path, 'rb') as f:
                    pdf_data = f.read()
                
                col1, col2, col3 = st.columns([1, 2, 1])
                
                with col2:
                    st.download_button(
                        label="📥 Download PDF",
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
                **Domain:** {chapter_info['domain']}  
                **Size:** {file_size_mb:.1f}MB  
                **Time:** {total_time:.1f}s
                """)
                
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
        
        finally:
            # Cleanup
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
    
    # Footer
    st.write("---")
    st.markdown("""
    <div style='text-align: center; color: gray;'>
    <p>Made with ❤️ for @moonread_channel | v1.0 Web</p>
    <p>No rate limits • No queues • Direct download</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
