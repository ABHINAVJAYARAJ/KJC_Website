// script.js
// Author: Abhinav Jayaraj
// Contact: jayarajabhinav@gmail.com

// Set the published Google Forms URL before accepting client enquiries.
const GOOGLE_FORM_URL = '';
const THEME_STORAGE_KEY = 'kjc-theme';

const navigation = document.querySelector('#nav');
const menuButton = document.querySelector('#menu');
const navigationLinks = document.querySelector('#links');
const themeButton = document.querySelector('#theme-toggle');
const themeLabel = themeButton.querySelector('.theme-label');
const themeMeta = document.querySelector('meta[name="theme-color"]');
const formStatus = document.querySelector('#form-link-status');

function closeMobileMenu() {
  navigation.classList.remove('is-open');
  menuButton.setAttribute('aria-expanded', 'false');
  menuButton.textContent = 'Menu +';
}

function initialiseMobileMenu() {
  menuButton.addEventListener('click', () => {
    const isOpen = navigation.classList.toggle('is-open');
    menuButton.setAttribute('aria-expanded', String(isOpen));
    menuButton.textContent = isOpen ? 'Close −' : 'Menu +';
  });

  navigationLinks.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', closeMobileMenu);
  });
}

function getSavedTheme() {
  try {
    return localStorage.getItem(THEME_STORAGE_KEY) === 'dark' ? 'dark' : 'light';
  } catch {
    // Private browsing and restricted environments may block storage.
    return 'light';
  }
}

function applyTheme(theme) {
  const isDark = theme === 'dark';
  document.documentElement.dataset.theme = isDark ? 'dark' : 'light';
  themeButton.setAttribute('aria-pressed', String(isDark));
  themeButton.setAttribute('aria-label', isDark ? 'Switch to light mode' : 'Switch to dark mode');
  themeButton.title = isDark ? 'Switch to light mode' : 'Switch to dark mode';
  themeLabel.textContent = isDark ? 'Light' : 'Dark';
  themeMeta.setAttribute('content', isDark ? '#151719' : '#f8f7f4');
}

function initialiseTheme() {
  applyTheme(getSavedTheme());

  themeButton.addEventListener('click', () => {
    const nextTheme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    applyTheme(nextTheme);

    try {
      localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
    } catch {
      // The selected theme still applies if storage is unavailable.
    }
  });
}

function initialiseEnquiryLinks() {
  const isGoogleForm = /^https:\/\/(?:docs\.google\.com\/forms\/|forms\.gle\/)/.test(GOOGLE_FORM_URL);

  document.querySelectorAll('[data-kjc-form]').forEach((link) => {
    if (isGoogleForm) {
      link.href = GOOGLE_FORM_URL;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      return;
    }

    // Keep general enquiry links pointed at Contact until a verified form URL is available.
    if (link.classList.contains('form-open')) {
      link.addEventListener('click', (event) => {
        event.preventDefault();
        formStatus.textContent = 'The enquiry form is not available yet. Please check back soon.';
      });
    }
  });
}

initialiseMobileMenu();
initialiseTheme();
initialiseEnquiryLinks();


// Show the initials fallback if an approved portrait cannot be loaded.
document.querySelectorAll('.profile-portrait img').forEach((image) => {
  image.addEventListener('error', () => image.closest('.profile-portrait').remove());
});
