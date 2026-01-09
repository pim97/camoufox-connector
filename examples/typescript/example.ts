/**
 * Camoufox Connector - TypeScript Example
 *
 * This example demonstrates how to connect to Camoufox from TypeScript
 * using Playwright's remote connection feature.
 *
 * Prerequisites:
 *   npm install playwright typescript ts-node @types/node
 *
 * Run:
 *   npx ts-node example.ts
 *
 * Start the connector server first:
 *   camoufox-connector --mode pool --pool-size 3
 */

import { firefox, Browser, Page } from 'playwright';

const API_URL: string = process.env.CAMOUFOX_API || 'http://localhost:8080';

interface EndpointResponse {
    endpoint: string;
}

interface HealthResponse {
    status: string;
    mode: string;
    instances: Array<{
        index: number;
        healthy: boolean;
        endpoint: string | null;
    }>;
}

interface StatsResponse {
    mode: string;
    total_instances: number;
    healthy_instances: number;
    active_connections: number;
    total_connections: number;
}

/**
 * Get the next available browser endpoint using round-robin
 */
async function getNextEndpoint(): Promise<string> {
    try {
        const response = await fetch(`${API_URL}/next`);
        
        if (!response.ok) {
            throw new Error(`Failed to get endpoint: ${response.statusText}`);
        }
        
        const data: EndpointResponse = await response.json();
        return data.endpoint;
    } catch (error) {
        if (error instanceof Error && (error.message.includes('fetch failed') || error.message.includes('ECONNREFUSED'))) {
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
async function getAllEndpoints(): Promise<string[]> {
    const response = await fetch(`${API_URL}/endpoints`);
    const data = await response.json();
    return data.endpoints;
}

/**
 * Check server health
 */
async function checkHealth(): Promise<boolean> {
    try {
        const response = await fetch(`${API_URL}/health`);
        const data: HealthResponse = await response.json();
        
        console.log('Server health:', JSON.stringify(data, null, 2));
        return data.status === 'healthy';
    } catch (error) {
        console.error(
            `\n❌ Cannot connect to Camoufox Connector at ${API_URL}\n` +
            `Please start the server first:\n` +
            `  camoufox-connector --mode pool --pool-size 3\n`
        );
        return false;
    }
}

/**
 * Get pool statistics
 */
async function getStats(): Promise<StatsResponse> {
    const response = await fetch(`${API_URL}/stats`);
    return response.json();
}

/**
 * Basic example: Connect and navigate to a page
 */
async function basicExample(): Promise<void> {
    console.log('\n=== Basic Example ===\n');
    
    // Get a browser endpoint using round-robin
    const endpoint = await getNextEndpoint();
    console.log(`Connecting to: ${endpoint}`);
    
    // Connect to Camoufox via WebSocket
    const browser: Browser = await firefox.connect(endpoint);
    
    try {
        // Create a new page
        const page: Page = await browser.newPage();
        
        // Navigate to a test page
        await page.goto('https://httpbin.org/headers');
        
        // Get page content
        const content = await page.textContent('body');
        console.log('Response:', content);
        
        // Take a screenshot
        await page.screenshot({ path: 'screenshot.png' });
        console.log('Screenshot saved to screenshot.png');
        
    } finally {
        // Close the connection
        await browser.close();
    }
}

/**
 * Pool example: Distribute work across multiple browsers
 */
async function poolExample(): Promise<void> {
    console.log('\n=== Pool Example ===\n');
    
    const urls: string[] = [
        'https://httpbin.org/ip',
        'https://httpbin.org/user-agent',
        'https://httpbin.org/headers',
        'https://httpbin.org/get',
        'https://httpbin.org/cookies',
    ];
    
    interface Result {
        url: string;
        content: string;
    }
    
    // Process URLs in parallel, each getting a different browser
    const results: Result[] = await Promise.all(urls.map(async (url): Promise<Result> => {
        // Each call to /next gets the next browser in rotation
        const endpoint = await getNextEndpoint();
        console.log(`Processing ${url} via ${endpoint}`);
        
        const browser = await firefox.connect(endpoint);
        
        try {
            const page = await browser.newPage();
            await page.goto(url);
            
            const content = await page.textContent('body') || '';
            return { url, content: content.substring(0, 100) + '...' };
            
        } finally {
            await browser.close();
        }
    }));
    
    console.log('\nResults:');
    results.forEach(r => console.log(`  ${r.url}: ${r.content}`));
}

/**
 * Stats example: Display pool statistics
 */
async function statsExample(): Promise<void> {
    console.log('\n=== Stats Example ===\n');
    
    const stats = await getStats();
    
    console.log(`Mode: ${stats.mode}`);
    console.log(`Total instances: ${stats.total_instances}`);
    console.log(`Healthy instances: ${stats.healthy_instances}`);
    console.log(`Active connections: ${stats.active_connections}`);
    console.log(`Total connections: ${stats.total_connections}`);
}

// Main execution
async function main(): Promise<void> {
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
        await statsExample();
        
        console.log('\n✓ All examples completed successfully!\n');
        
    } catch (error) {
        console.error('Error:', error instanceof Error ? error.message : error);
        process.exit(1);
    }
}

main();
