import { createUserContext } from '../src/auth/user_context';
import { filterUserContext } from '../src/auth/auth_filter';

export function runTests(): boolean {
  const ctx = createUserContext('usr_123', 'ten_456', ['admin']);
  if (ctx.user_id !== 'usr_123') {
    throw new Error('user_id mismatch');
  }
  return filterUserContext(ctx);
}
