document.addEventListener('DOMContentLoaded', () => {

    // --- Radial Menu Logic ---
    const radialMenu = document.querySelector('.radial-menu');
    const menuCenter = document.querySelector('.menu-center');
    if (radialMenu && menuCenter) {
        menuCenter.addEventListener('click', () => {
            radialMenu.classList.toggle('open');
        });
    }

    // --- File Input Display Logic ---
    const fileInputs = document.querySelectorAll('input[type="file"]');
    fileInputs.forEach(input => {
        const originalLabel = input.previousElementSibling?.textContent || '';
        input.addEventListener('change', (e) => {
            const fileName = e.target.files[0]?.name || 'No file selected';
            const label = input.previousElementSibling;
            if (label && label.tagName === 'LABEL') {
                // We store the original label text to reset it, but this is a simple version
                label.textContent = originalLabel.replace(/:.*/, `: ${fileName}`);
            }
        });
    });

    // --- Prevent Form Resubmission on Refresh ---
    if (window.history.replaceState) {
        window.history.replaceState(null, null, window.location.href);
    }
});


/**
 * Copy to Clipboard Function
 * It's defined on the window object so it can be called directly
 * from the 'onclick' attribute in your HTML template.
 */
window.copyToClipboard = function(text) {
    if (!navigator.clipboard) {
        // Fallback for older browsers or non-secure contexts
        try {
            const textArea = document.createElement("textarea");
            textArea.value = text;
            textArea.style.position = "fixed"; // Avoid scrolling
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            alert('Copied to clipboard!');
        } catch (err) {
            alert('Failed to copy text.');
        }
        return;
    }

    // Modern, secure way to copy
    navigator.clipboard.writeText(text).then(() => {
        alert('Copied to clipboard!');
    }, (err) => {
        alert('Failed to copy text.');
        console.error('Could not copy text: ', err);
    });
}