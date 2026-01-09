/**
 * Camoufox Connector - Node.js Example
 *
 * This example demonstrates how to connect to Camoufox from Node.js
 * using Playwright's remote connection feature.
 *
 * Prerequisites:
 *   npm install playwright
 *
 * Start the connector server first:
 *   camoufox-connector --mode pool --pool-size 3
 */

import { firefox } from 'playwright';

const API_URL = process.env.CAMOUFOX_API || 'http://localhost:8080';

/**
 * Get the next available browser endpoint from the connector
 */
async function getNextEndpoint() {
    try {
        const response = await fetch(`${API_URL}/next`);
        
        if (!response.ok) {
            throw new Error(`Failed to get endpoint: ${response.statusText}`);
        }
        
        const data = await response.json();
        return data.endpoint;
    } catch (error) {
        if (error.message.includes('fetch failed') || error.code === 'ECONNREFUSED') {
            throw new Error(
                `Cannot connect to Camoufox Connector at ${API_URL}.\n` +
                `Please make sure the server is running:\n` +
                `  camoufox-connector --mode pool --pool-size 3`
            );
        }
        throw error;
    }
}

/**
 * Get all available browser endpoints
 */
async function getAllEndpoints() {
    try {
        const response = await fetch(`${API_URL}/endpoints`);
        
        if (!response.ok) {
            throw new Error(`Failed to get endpoints: ${response.statusText}`);
        }
        
        const data = await response.json();
        return data.endpoints;
    } catch (error) {
        if (error.message.includes('fetch failed') || error.code === 'ECONNREFUSED') {
            throw new Error(
                `Cannot connect to Camoufox Connector at ${API_URL}.\n` +
                `Please make sure the server is running:\n` +
                `  camoufox-connector --mode pool --pool-size 3`
            );
        }
        throw error;
    }
}

/**
 * Check server health
 */
async function checkHealth() {
    try {
        const response = await fetch(`${API_URL}/health`);
        const data = await response.json();
        
        console.log('Server health:', data);
        return data.status === 'healthy';
    } catch (error) {
        if (error.message.includes('fetch failed') || error.code === 'ECONNREFUSED') {
            console.error(
                `\n❌ Cannot connect to Camoufox Connector at ${API_URL}\n` +
                `Please start the server first:\n` +
                `  camoufox-connector --mode pool --pool-size 3\n`
            );
            return false;
        }
        throw error;
    }
}

/**
 * Basic example: Connect and navigate to a page
 */
async function basicExample() {
    console.log('\n=== Basic Example ===\n');
    
    // Get a browser endpoint using round-robin
    const endpoint = await getNextEndpoint();
    console.log(`Connecting to: ${endpoint}`);
    
    // Connect to Camoufox via WebSocket
    const browser = await firefox.connect(endpoint);
    
    try {
        // Create a new page
        const page = await browser.newPage();
        
        // Navigate to a test page
        await page.goto('https://httpbin.org/headers');
        
        // Get page content
        const content = await page.textContent('body');
        console.log('Response:', content);
        
        // Take a screenshot
        await page.screenshot({ path: 'screenshot.png' });
        console.log('Screenshot saved to screenshot.png');
        
    } finally {
        // Close the connection (not the browser, it stays running)
        await browser.close();
    }
}

/**
 * Pool example: Distribute work across multiple browsers
 */
async function poolExample() {
    console.log('\n=== Pool Example ===\n');
    
    const urls = [
        'https://httpbin.org/ip',
        'https://httpbin.org/user-agent',
        'https://httpbin.org/headers',
        'https://httpbin.org/get',
        'https://httpbin.org/cookies',
    ];
    
    // Process URLs in parallel, each getting a different browser
    const results = await Promise.all(urls.map(async (url) => {
        // Each call to /next gets the next browser in rotation
        const endpoint = await getNextEndpoint();
        console.log(`Processing ${url} via ${endpoint}`);
        
        const browser = await firefox.connect(endpoint);
        
        try {
            const page = await browser.newPage();
            await page.goto(url);
            
            const content = await page.textContent('body');
            return { url, content: content.substring(0, 100) + '...' };
            
        } finally {
            await browser.close();
        }
    }));
    
    console.log('\nResults:');
    results.forEach(r => console.log(`  ${r.url}: ${r.content}`));
}

/**
 * Session persistence example
 */
async function sessionExample() {
    console.log('\n=== Session Example ===\n');
    
    // Get all endpoints and pick one for persistent session
    const endpoints = await getAllEndpoints();
    const endpoint = endpoints[0];
    
    console.log(`Using fixed endpoint for session: ${endpoint}`);
    
    // First connection: login
    let browser = await firefox.connect(endpoint);
    let page = await browser.newPage();
    
    // Simulate setting a cookie
    await page.goto('https://httpbin.org/cookies/set/session/abc123');
    console.log('Session cookie set');
    
    await browser.close();
    
    // Second connection: verify cookie persists
    browser = await firefox.connect(endpoint);
    page = await browser.newPage();
    
    await page.goto('https://httpbin.org/cookies');
    const cookies = await page.textContent('body');
    console.log('Cookies in second connection:', cookies);
    
    await browser.close();
}

// Main execution
async function main() {
    try {
        // Check if server is healthy
        const healthy = await checkHealth();
        
        if (!healthy) {
            console.error('Server is not healthy. Please start the connector first.');
            process.exit(1);
        }
        
        // Run examples
        await basicExample();
        await poolExample();
        await sessionExample();
        
        console.log('\n✓ All examples completed successfully!\n');
        
    } catch (error) {
        console.error('Error:', error.message);
        process.exit(1);
    }
}

main();
