/**
 * Frontend JWT Authentication Module
 * Task: T030a - Client-side authentication
 *
 * Features:
 * - localStorage token management
 * - Automatic Authorization header injection
 * - 401/403 handling → redirect to login
 * - Token expiry detection
 * - Development mode bypass
 */

class AuthManager {
    constructor() {
        this.tokenKey = 'utxoracle_jwt_token';
        this.apiBase = window.location.origin;
    }

    /**
     * Store JWT token in localStorage
     * @param {string} token - JWT token
     */
    setToken(token) {
        if (!token || typeof token !== 'string') {
            console.error('Invalid token provided to setToken');
            return false;
        }

        try {
            localStorage.setItem(this.tokenKey, token);
            console.log('✅ Token stored successfully');
            return true;
        } catch (e) {
            console.error('Failed to store token:', e);
            return false;
        }
    }

    /**
     * Retrieve JWT token from localStorage
     * @returns {string|null} JWT token or null
     */
    getToken() {
        try {
            return localStorage.getItem(this.tokenKey);
        } catch (e) {
            console.error('Failed to retrieve token:', e);
            return null;
        }
    }

    /**
     * Remove JWT token from localStorage
     */
    clearToken() {
        try {
            localStorage.removeItem(this.tokenKey);
            console.log('✅ Token cleared');
        } catch (e) {
            console.error('Failed to clear token:', e);
        }
    }

    /**
     * Check if user is authenticated
     * @returns {boolean} True if token exists
     */
    isAuthenticated() {
        const token = this.getToken();
        return token !== null && token !== '';
    }

    /**
     * Parse JWT token to extract payload (client-side validation only)
     * WARNING: This does NOT verify signature - server must validate!
     * @param {string} token - JWT token
     * @returns {object|null} Decoded payload or null
     */
    decodeToken(token) {
        if (!token) return null;

        try {
            const parts = token.split('.');
            if (parts.length !== 3) {
                console.error('Invalid JWT format');
                return null;
            }

            const payload = parts[1];
            const decoded = JSON.parse(atob(payload));
            return decoded;
        } catch (e) {
            console.error('Failed to decode token:', e);
            return null;
        }
    }

    /**
     * Check if token is expired (client-side check only)
     * @returns {boolean} True if token is expired
     */
    isTokenExpired() {
        const token = this.getToken();
        if (!token) return true;

        const payload = this.decodeToken(token);
        if (!payload || !payload.exp) {
            console.warn('Token has no expiry field');
            return false; // Assume valid if no exp
        }

        const now = Math.floor(Date.now() / 1000);
        const expired = payload.exp < now;

        if (expired) {
            console.warn('Token expired at', new Date(payload.exp * 1000));
        }

        return expired;
    }

    /**
     * Make authenticated API request with auto-retry on 401
     * @param {string} url - API endpoint
     * @param {object} options - fetch() options
     * @returns {Promise<Response>} Fetch response
     */
    async authenticatedFetch(url, options = {}) {
        const token = this.getToken();

        // Check if token exists
        if (!token) {
            console.error('No token available - redirecting to login');
            this.redirectToLogin();
            throw new Error('Authentication required');
        }

        // Check if token is expired (client-side check)
        if (this.isTokenExpired()) {
            console.warn('Token expired - redirecting to login');
            this.clearToken();
            this.redirectToLogin();
            throw new Error('Token expired');
        }

        // Inject Authorization header
        const headers = {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
            ...(options.headers || {})
        };

        const fetchOptions = {
            ...options,
            headers
        };

        try {
            const response = await fetch(url, fetchOptions);

            // Handle authentication errors
            if (response.status === 401) {
                console.error('401 Unauthorized - clearing token and redirecting');
                this.clearToken();
                this.redirectToLogin();
                throw new Error('Unauthorized - token invalid or expired');
            }

            // Handle forbidden
            if (response.status === 403) {
                console.error('403 Forbidden - insufficient permissions');
                throw new Error('Forbidden - insufficient permissions');
            }

            // Handle rate limiting
            if (response.status === 429) {
                console.error('429 Too Many Requests - rate limit exceeded');
                throw new Error('Rate limit exceeded - try again later');
            }

            return response;
        } catch (error) {
            console.error('Authenticated fetch failed:', error);
            throw error;
        }
    }

    /**
     * Redirect to login page
     * @param {string} returnUrl - URL to return after login
     */
    redirectToLogin(returnUrl = null) {
        const currentPath = returnUrl || window.location.pathname;
        const loginUrl = `/login.html?return=${encodeURIComponent(currentPath)}`;

        console.log('Redirecting to login:', loginUrl);
        window.location.href = loginUrl;
    }

    /**
     * Logout user (clear token and redirect to login)
     */
    logout() {
        this.clearToken();
        console.log('✅ Logged out');
        this.redirectToLogin('/');
    }

    /**
     * Get token info for debugging
     * @returns {object} Token information
     */
    getTokenInfo() {
        const token = this.getToken();
        if (!token) {
            return { authenticated: false };
        }

        const payload = this.decodeToken(token);
        if (!payload) {
            return { authenticated: true, valid: false };
        }

        const now = Math.floor(Date.now() / 1000);
        const expiresIn = payload.exp ? payload.exp - now : null;

        return {
            authenticated: true,
            valid: true,
            clientId: payload.client_id || 'unknown',
            permissions: payload.permissions || [],
            expiresAt: payload.exp ? new Date(payload.exp * 1000).toISOString() : null,
            expiresIn: expiresIn,
            expired: expiresIn !== null ? expiresIn <= 0 : false
        };
    }
}

// Export singleton instance
const authManager = new AuthManager();

// Global error handler for unhandled authentication errors
window.addEventListener('unhandledrejection', (event) => {
    if (event.reason && event.reason.message) {
        const msg = event.reason.message.toLowerCase();
        if (msg.includes('unauthorized') || msg.includes('authentication required')) {
            console.error('Unhandled authentication error:', event.reason);
            // Don't redirect here - let specific handlers deal with it
        }
    }
});

// Log auth status on page load
console.log('🔐 Auth Manager initialized');
console.log('Authentication status:', authManager.getTokenInfo());
