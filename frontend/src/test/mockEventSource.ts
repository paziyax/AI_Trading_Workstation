/**
 * Minimal EventSource double. Tests can open, error, and push a JSON frame to
 * the single instance a provider created.
 */
export class MockEventSource {
  static instances: MockEventSource[] = [];

  url: string;
  readyState = 0;
  withCredentials = false;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  close() {
    this.readyState = 2;
  }

  addEventListener() {}
  removeEventListener() {}
  dispatchEvent() {
    return true;
  }

  emitOpen() {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }

  emitFrame(frame: unknown) {
    this.onmessage?.(
      new MessageEvent("message", { data: JSON.stringify(frame) }),
    );
  }

  emitError() {
    this.onerror?.(new Event("error"));
  }

  static get latest(): MockEventSource | undefined {
    return MockEventSource.instances[MockEventSource.instances.length - 1];
  }
}
