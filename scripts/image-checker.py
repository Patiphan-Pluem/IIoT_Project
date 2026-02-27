import os
import re
import subprocess

SEARCH_DIR = "./service-apps"

def get_images_from_yaml(directory):
    images = set()
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".yaml") or file.endswith(".yml"):
                with open(os.path.join(root, file), 'r') as f:
                    content = f.read()
                    found = re.findall(r'image:\s*"?([^"\s]+)"?', content)
                    for img in found:
                        if "{{" not in img:
                            images.add(img)
    return images

def check_image_existence(image):
    full_path = f"docker://{image}" if "://" not in image else image
    try:
        subprocess.run(["skopeo", "inspect", full_path], 
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        return True, "✅ Accessible"
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode().split('\n')[0]
        return False, f"❌ Denied/NotFound: {error_msg}"

print(f"🚀 Scanning for images in {SEARCH_DIR}...")
images_to_check = get_images_from_yaml(SEARCH_DIR)

    
print(f"🔍 Found {len(images_to_check)} unique images. Starting validation...\n")

all_passed = True  

for img in images_to_check:
    status, msg = check_image_existence(img)
    print(f"{img:<50} | {msg}")
    if not status:
        all_passed = False  


if not all_passed:
    print("\n❌ CI Failed: Some images are not accessible.")
    exit(1)  
else:
    print("\n✅ CI Passed: All images are accessible.")
    exit(0)