export interface OperatorSession {
  authenticated: boolean;
  username: string | null;
  warning: string | null;
}

export interface OperatorLoginPayload {
  username: string;
  password: string;
}
