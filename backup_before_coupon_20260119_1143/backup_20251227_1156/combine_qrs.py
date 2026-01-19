import os
import math
from PIL import Image, ImageDraw, ImageFont

def combine_qrs():
    source_dir = 'branch_qrs'
    output_file = 'combined_qrs.jpg'
    
    # A4 size at 300 DPI (approx)
    a4_width = 2480
    a4_height = 3508
    
    # Create white canvas
    canvas = Image.new('RGB', (a4_width, a4_height), 'white')
    draw = ImageDraw.Draw(canvas)
    
    # Get all images
    files = [f for f in os.listdir(source_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    if not files:
        print("No images found in branch_qrs directory.")
        return

    print(f"Found {len(files)} images.")

    # Layout settings
    cols = 2
    rows = math.ceil(len(files) / cols)
    
    # Margins and spacing
    margin_x = 150
    margin_y = 150
    
    # Calculate available space
    available_width = a4_width - (2 * margin_x)
    available_height = a4_height - (2 * margin_y)
    
    col_width = available_width // cols
    row_height = available_height // rows
    
    # Padding inside each cell
    padding = 100 
    
    # Determine QR code size (square) to fit in the cell with padding
    # We leave room for text below the QR code as well
    text_allowance = 100
    max_qr_size = min(col_width - padding, row_height - padding - text_allowance)
    
    # Font setup
    try:
        # Use Malgun Gothic for Korean support (Windows standard)
        font = ImageFont.truetype("malgun.ttf", 60)
    except IOError:
        print("Malgun Gothic font not found, trying Arial.")
        try:
             font = ImageFont.truetype("arial.ttf", 60)
        except IOError:
             print("Arial font not found, using default.")
             font = ImageFont.load_default()

    for idx, filename in enumerate(files):
        img_path = os.path.join(source_dir, filename)
        try:
            img = Image.open(img_path)
            
            # Resize image carefully with high quality
            img = img.resize((max_qr_size, max_qr_size), Image.Resampling.LANCZOS)
            
            # Grid position
            col = idx % cols
            row = idx // cols
            
            # Center in cell
            cell_x = margin_x + (col * col_width)
            cell_y = margin_y + (row * row_height)
            
            # Calculate positions to center content in cell
            qr_x = cell_x + (col_width - max_qr_size) // 2
            
            # Vertical center including text space
            content_height = max_qr_size + 30 + 60 # qr + gap + roughly text height
            start_y = cell_y + (row_height - content_height) // 2
            
            qr_y = start_y
            
            # Paste QR code
            canvas.paste(img, (qr_x, qr_y))
            
            # Draw text
            text_str = filename
            
            # Calculate text width to center it
            if hasattr(draw, 'textbbox'):
                 bbox = draw.textbbox((0, 0), text_str, font=font)
                 text_width = bbox[2] - bbox[0]
            else:
                 # Fallback for older Pillow versions
                 text_width = draw.textlength(text_str, font=font)
                 
            text_x = cell_x + (col_width - text_width) // 2
            text_y = qr_y + max_qr_size + 30 # 30px gap below QR
            
            draw.text((text_x, text_y), text_str, fill="black", font=font)
            
            print(f"Processed {filename}")
            
        except Exception as e:
            print(f"Failed to process {filename}: {e}")

    # Save result
    canvas.save(output_file, quality=95)
    print(f"Successfully saved {output_file}")

if __name__ == "__main__":
    combine_qrs()
