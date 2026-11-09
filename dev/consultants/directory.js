// directory.js
// Author: Abhinav Jayaraj
// Contact: jayarajabhinav@gmail.com

const statusSection = document.querySelector('#consultants-status');
const directorySection = document.querySelector('#consultants-directory');
const directoryList = document.querySelector('#consultants-list');
const searchInput = document.querySelector('#consultant-search');
const focusSelect = document.querySelector('#consultant-focus');
const statusSelect = document.querySelector('#consultant-status');
const countLabel = document.querySelector('#consultants-count');
const emptyMessage = document.querySelector('#consultants-empty');

function createTextElement(tag, className, text) {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text;
  return element;
}

// A missing photograph keeps the original text-only directory layout.
function createPersonRow(person) {
  const row = document.createElement('a');
  row.className = 'person-row';
  row.href = `${encodeURIComponent(person.slug)}/`;
  row.setAttribute('aria-label', `View ${person.name}'s profile`);

  if (person.photo) {
    const portrait = createTextElement('span', 'person-portrait', '');
    const image = document.createElement('img');
    image.src = `../assets/consultants/${encodeURIComponent(person.photo)}`;
    image.alt = '';
    image.width = 64;
    image.height = 72;
    image.loading = 'lazy';
    // Keep the original row layout if an image fails to load.
    image.addEventListener('error', () => {
      portrait.remove();
      row.classList.remove('has-photo');
    });
    portrait.append(image);
    row.append(portrait);
    row.classList.add('has-photo');
  }

  const summary = createTextElement('div', 'person-summary', '');
  summary.append(createTextElement('strong', '', person.name));
  summary.append(createTextElement('span', '', (person.status === 'former' ? 'Former · ' : '') + person.role));

  row.append(summary);
  row.append(createTextElement('span', 'person-area', person.focus || 'Consultant'));
  row.append(createTextElement('span', 'row-arrow', '↗'));
  return row;
}

// Keep the A–Z index consistent with institutional directories.
function surnameKey(person) {
  return (person.sortName || person.name.trim().split(/\s+/).at(-1)).toLocaleLowerCase('en-GB');
}

function renderDirectory() {
  const term = searchInput.value.trim().toLocaleLowerCase('en-GB');
  const expertise = focusSelect.value;
  const status = statusSelect.value;
  const filtered = CONSULTANTS.filter((person) => {
    const text = [person.name, person.role, person.focus, ...(person.expertise || [])].join(' ').toLocaleLowerCase('en-GB');
    return text.includes(term) && (!expertise || (person.expertise || []).includes(expertise))
      && (!status || (person.status || 'active') === status);
  }).sort((a, b) => surnameKey(a).localeCompare(surnameKey(b), 'en-GB') || a.name.localeCompare(b.name, 'en-GB'));

  const fragment = document.createDocumentFragment();
  const grouped = new Map();
  filtered.forEach((person) => {
    const letter = surnameKey(person).charAt(0).toLocaleUpperCase('en-GB');
    if (!grouped.has(letter)) grouped.set(letter, []);
    grouped.get(letter).push(person);
  });

  for (const [letter, people] of grouped) {
    const section = createTextElement('section', 'directory-letter', '');
    const heading = createTextElement('h2', 'letter-heading', letter);
    section.append(heading);
    people.forEach((person) => section.append(createPersonRow(person)));
    fragment.append(section);
  }

  directoryList.replaceChildren(fragment);
  countLabel.textContent = `${filtered.length} consultant${filtered.length === 1 ? '' : 's'}`;
  emptyMessage.hidden = filtered.length !== 0;
}

function initialiseDirectory() {
  if (!PUBLISH_CONSULTANTS || CONSULTANTS.length === 0) return;

  const focusAreas = [...new Set(CONSULTANTS.flatMap((person) => person.expertise || []))]
    .sort((a, b) => a.localeCompare(b, 'en-GB'));
  focusAreas.forEach((focus) => {
    const option = document.createElement('option');
    option.value = focus;
    option.textContent = focus;
    focusSelect.append(option);
  });

  statusSection.hidden = true;
  directorySection.hidden = false;
  searchInput.addEventListener('input', renderDirectory);
  focusSelect.addEventListener('change', renderDirectory);
  statusSelect.addEventListener('change', renderDirectory);
  renderDirectory();
}

initialiseDirectory();
