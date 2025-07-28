from flask import Flask, render_template, request, send_from_directory, url_for,redirect,session
import os
import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken
import numpy as np
from PIL import Image
import cv2
from scipy.io.wavfile import write, read
from io import BytesIO
import tempfile

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.secret_key = os.urandom(24)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Encryption Utilities ---
def generate_key(keyword):
    key = hashlib.sha256(keyword.encode()).digest()
    return base64.urlsafe_b64encode(key)

def encrypt_text(text, keyword):
    key = generate_key(keyword)
    fernet = Fernet(key)
    return fernet.encrypt(text.encode()).decode()

def decrypt_text(encrypted_text, keyword):
    key = generate_key(keyword)
    fernet = Fernet(key)
    try:
        return fernet.decrypt(encrypted_text.encode()).decode()
    except InvalidToken:
        raise ValueError("Invalid keyword or corrupt data - decryption failed")

# --- Image Steganography ---
def hide_text_in_image(image, text, keyword):
    img = Image.open(image).convert("RGB")
    pixels = np.array(img)
    
    encrypted_text = encrypt_text(text, keyword)
    delimiter = '1111111111111110'
    binary_text = ''.join(format(ord(c), '08b') for c in encrypted_text) + delimiter
    
    if len(binary_text) > (pixels.size):
        raise ValueError("Text is too large to hide in this image")
    
    flat_pixels = pixels.flatten()
    for i in range(len(binary_text)):
        flat_pixels[i] = (flat_pixels[i] & 0xFE) | int(binary_text[i])
    
    pixels = flat_pixels.reshape(img.size[1], img.size[0], 3)
    
    output = BytesIO()
    Image.fromarray(pixels).save(output, format='PNG')
    return output.getvalue()

def extract_text_from_image(image, keyword):
    img = Image.open(image).convert("RGB")
    pixels = np.array(img).flatten()

    binary_data = ''
    delimiter = '1111111111111110'
    
    for pixel_value in pixels:
        binary_data += str(pixel_value & 1)
        if binary_data.endswith(delimiter):
            break
    else:
        raise ValueError("No hidden message found")

    binary_str = binary_data[:-len(delimiter)]
    encrypted_text = bytearray(int(binary_str[i:i+8], 2) for i in range(0, len(binary_str), 8))
    return decrypt_text(encrypted_text.decode(errors='ignore'), keyword)

# --- Audio <-> Image Conversion ---
def image_to_audio(image_file, keyword):
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_img:
        image_file.save(tmp_img.name)
        tmp_img_path = tmp_img.name
    
    try:
        keyword_hash = hashlib.sha256(keyword.encode()).hexdigest()[:8]
        output_audio = f"audio_{keyword_hash}.wav"
        shape_file = f"shape_{keyword_hash}.npy"

        img = cv2.imread(tmp_img_path, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Invalid image file")
        
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        shape_path = os.path.join(app.config['UPLOAD_FOLDER'], shape_file)
        np.save(shape_path, img.shape)

        flat_img = img.flatten().astype(np.float32)
        normalized = (flat_img / 255.0) * 2 - 1
        audio_data = np.int16(normalized * 32767)

        audio_path = os.path.join(app.config['UPLOAD_FOLDER'], output_audio)
        write(audio_path, 44100, audio_data)

        return output_audio, shape_file
    finally:
        os.unlink(tmp_img_path)

def audio_to_image(audio_file, shape_file, keyword):
    keyword_hash = hashlib.sha256(keyword.encode()).hexdigest()[:8]
    expected_shape_file = f"shape_{keyword_hash}.npy"
    shape_path = os.path.join(app.config['UPLOAD_FOLDER'], expected_shape_file)

    if not os.path.exists(shape_path):
        if shape_file:
            with tempfile.NamedTemporaryFile(suffix='.npy', delete=False) as tmp_shape:
                shape_file.save(tmp_shape.name)
                temp_shape_path = tmp_shape.name
        else:
            raise ValueError("No shape file found for this keyword")
    else:
        temp_shape_path = shape_path

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_audio:
        audio_file.save(tmp_audio.name)
        tmp_audio_path = tmp_audio.name

    try:
        original_shape = tuple(np.load(temp_shape_path))
        sample_rate, audio_data = read(tmp_audio_path)

        # Convert audio back to pixel values
        normalized = audio_data.astype(np.float32) / 32767
        pixel_values = ((normalized + 1) / 2 * 255).astype(np.uint8)

        expected_size = np.prod(original_shape)
        pixel_values = pixel_values[:expected_size]
        recovered_img = pixel_values.reshape(original_shape).astype(np.uint8)
        recovered_img = cv2.cvtColor(recovered_img, cv2.COLOR_RGB2BGR)

        output_image = f"recovered_{keyword_hash}.png"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_image)
        cv2.imwrite(output_path, recovered_img)

        return output_image
    finally:
        os.unlink(tmp_audio_path)
        if temp_shape_path != shape_path:
            os.unlink(temp_shape_path)

# --- Flask Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/tool/<mode>', methods=['GET', 'POST'])
def tool(mode):
    result = None
    output_audio = None
    output_shape = None
    output_image = None
    error = None
    
    if request.method == 'POST':
        keyword = request.form.get('keyword', '').strip()
        if not keyword:
            error = "Keyword cannot be empty."
        else:
            try:
                if mode in ['text-encrypt', 'text-decrypt']:
                    text = request.form.get('text', '').strip()
                    if not text:
                        error = "Text cannot be empty."
                    else:
                        result = encrypt_text(text, keyword) if mode == 'text-encrypt' else decrypt_text(text, keyword)
                
                elif mode in ['image-encrypt', 'image-decrypt']:
                    file = request.files.get('file')
                    if not file:
                        error = "Please select an image."
                    elif mode == 'image-encrypt':
                        text = request.form.get('text', '').strip()
                        if not text:
                            error = "Enter text to hide."
                        else:
                            img_data = hide_text_in_image(file, text, keyword)
                            filename = f"encrypted_{os.path.splitext(file.filename)[0]}.png"
                            with open(os.path.join(app.config['UPLOAD_FOLDER'], filename), 'wb') as f:
                                f.write(img_data)
                            output_image = filename
                    else:
                        result = extract_text_from_image(file, keyword)
                
                elif mode == 'audio-encrypt':
                    file = request.files.get('file')
                    if not file:
                        error = "Select an image to encode."
                    else:
                        output_audio, output_shape = image_to_audio(file, keyword)

                elif mode == 'audio-decrypt':
                    file = request.files.get('file')
                    shape_file = request.files.get('shape_file')
                    if not file or not shape_file:
                        error = "Audio and shape file required."
                    else:
                        output_image = audio_to_image(file, shape_file, keyword)

            except Exception as e:
                error = f"An error occurred: {str(e)}"
    
    return render_template('tool.html', 
                           mode=mode, 
                           result=result,
                           output_audio=output_audio,
                           output_shape=output_shape,
                           output_image=output_image,
                           error=error)

@app.route('/download/<filename>')
def download(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/about/')
def about():
    return render_template('about.html')

@app.route("/guide")
def guide():
    return render_template('guide.html')
@app.route("/donate")
def donate():
    return render_template("donate.html")

@app.route('/download-shape/<audio_filename>')
def download_shape(audio_filename):
    if audio_filename.startswith('audio_') and audio_filename.endswith('.wav'):
        keyword_hash = audio_filename[6:-4]
        shape_file = f"shape_{keyword_hash}.npy"
        return send_from_directory(app.config['UPLOAD_FOLDER'], shape_file, as_attachment=True)
    return "Invalid audio filename", 404

if __name__ == '__main__':
    app.run(debug=True)
