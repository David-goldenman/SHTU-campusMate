import {applyAccent} from '/assets/campus.js';

export function decorateCourse(element, course) {
  const value = course.appearance;
  if (!element || !value) return;
  applyAccent(element, value);
  element.dataset.department = value.key;
  const title = element.querySelector('h3,strong');
  if (value.icon === 'person-running' && title) {
    const image = document.createElement('img');
    image.className = 'course-sport-icon';
    image.src = '/assets/vendor/fontawesome/person-running.svg';
    image.alt = '';
    image.setAttribute('aria-hidden', 'true');
    title.prepend(image);
  }
  const label = document.createElement('span');
  label.className = 'course-department';
  label.textContent = value.label;
  label.title = course.department || value.label;
  element.append(label);
}
