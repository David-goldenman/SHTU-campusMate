import {chatSession} from './session.js';

export function mount(container, context) {
  container.hidden = true;
  return chatSession.attach(context);
}
