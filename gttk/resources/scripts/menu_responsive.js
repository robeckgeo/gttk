// Menu Responsive JavaScript for GeoTIFF ToolKit HTML Reports
// Handles responsive menu behavior (switches to icons-only mode when needed)

function adjustMenu() {
    const menuBar = document.querySelector('.menu-bar');
    if (!menuBar) return;

    menuBar.classList.remove('icons-only');
    
    if (menuBar.scrollWidth > menuBar.clientWidth) {
        menuBar.classList.add('icons-only');
    }
}

let resizeTimer;
window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(adjustMenu, 50);
});

// Run on load
adjustMenu();