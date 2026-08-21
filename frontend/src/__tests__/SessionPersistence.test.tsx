import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  clearStoredSessionId,
  getStoredSessionId,
  setStoredSessionId,
} from '../services/api';

describe('Session Persistence in LocalStorage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('stores and retrieves session ID from localStorage', () => {
    expect(getStoredSessionId()).toBeNull();

    setStoredSessionId('test-mehman-session-8821');
    expect(getStoredSessionId()).toBe('test-mehman-session-8821');
    expect(localStorage.getItem('mehman_session_id')).toBe('test-mehman-session-8821');
  });

  it('clears stored session ID on reset', () => {
    setStoredSessionId('test-mehman-session-8821');
    clearStoredSessionId();

    expect(getStoredSessionId()).toBeNull();
    expect(localStorage.getItem('mehman_session_id')).toBeNull();
  });
});
