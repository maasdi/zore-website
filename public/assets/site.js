const clipboardButtons = document.querySelectorAll('[data-copy-target]');
if (navigator.clipboard && window.isSecureContext) {
    for (const button of clipboardButtons) {
        const source = document.getElementById(button.dataset.copyTarget);
        if (!source) continue;
        button.hidden = false;
        button.addEventListener('click', async () => {
            const label = button.querySelector('span');
            const status = document.getElementById(button.dataset.copyStatus);
            try {
                await navigator.clipboard.writeText(source.textContent);
                label.textContent = 'Copied';
                if (status) status.textContent = 'Source copied to clipboard.';
            } catch {
                label.textContent = 'Select code';
                if (status) status.textContent = 'Clipboard unavailable. Select the source and copy it with your keyboard.';
            }
            window.setTimeout(() => { label.textContent = 'Copy'; }, 2200);
        });
    }
}
