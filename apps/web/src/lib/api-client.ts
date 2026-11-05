/**
 * SocietySphere Universal API Client Foundation
 * Handles request correlation, tenant context injection, and standardized RFC error parsing.
 */

export interface ApiErrorResponse {
  error: {
    code: string;
    message: string;
    request_id?: string;
    details?: Record<string, unknown>;
  };
}

export class ApiClientError extends Error {
  public code: string;
  public status: number;
  public requestId?: string;
  public details?: Record<string, unknown>;

  constructor(status: number, errorData: ApiErrorResponse['error']) {
    super(errorData.message);
    this.name = 'ApiClientError';
    this.status = status;
    this.code = errorData.code;
    this.requestId = errorData.request_id;
    this.details = errorData.details;
  }
}

export interface RequestOptions extends RequestInit {
  societyId?: string;
  authToken?: string;
}

export async function apiClient<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  const url = `${baseUrl}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;

  const headers = new Headers(options.headers);
  headers.set('Content-Type', 'application/json');
  headers.set('Accept', 'application/json');

  // Inject or propagate correlation ID
  const correlationId = `web-${Math.random().toString(36).substring(2, 11)}-${Date.now()}`;
  headers.set('X-Correlation-ID', correlationId);

  // Inject tenant context if provided
  if (options.societyId) {
    headers.set('X-Society-ID', options.societyId);
  }

  // Inject Bearer token if provided
  if (options.authToken) {
    headers.set('Authorization', `Bearer ${options.authToken}`);
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorPayload: ApiErrorResponse['error'];
    try {
      const json = await response.json();
      errorPayload = json.error || {
        code: 'HTTP_ERROR',
        message: response.statusText || 'Unknown server error',
        request_id: correlationId,
      };
    } catch {
      errorPayload = {
        code: `HTTP_${response.status}`,
        message: response.statusText || 'Network request failed',
        request_id: correlationId,
      };
    }
    throw new ApiClientError(response.status, errorPayload);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json() as Promise<T>;
}
