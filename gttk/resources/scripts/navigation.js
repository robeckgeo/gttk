/* eslint-env browser */

/**
 * Navigation JavaScript for GeoTIFF ToolKit HTML Reports
 * Handles scroll-based active link highlighting
 */

document.addEventListener("DOMContentLoaded", function() {
    const header = document.querySelector('.fixed-header');
    if (!header) return;

    const headerHeight = header.offsetHeight;
    document.documentElement.style.scrollPaddingTop = headerHeight + 'px';

    const menuLinks = document.querySelectorAll('.menu-link');
    const sections = Array.from(menuLinks).map(link => {
        const sectionId = link.getAttribute('href').substring(1);
        return document.getElementById(sectionId);
    }).filter(section => section !== null);

    if (sections.length === 0) return;

    function updateActiveLink() {
        let currentSectionId = null;
        const scrollPosition = window.scrollY;

        for (let i = sections.length - 1; i >= 0; i--) {
            const section = sections[i];
            if (section.offsetTop <= scrollPosition + headerHeight + 10) {
                currentSectionId = section.getAttribute('id');
                break;
            }
        }

        menuLinks.forEach(link => {
            const isActive = link.getAttribute('href') === `#${currentSectionId}`;
            if (isActive) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
    }

    updateActiveLink();
    window.addEventListener('scroll', updateActiveLink);
});