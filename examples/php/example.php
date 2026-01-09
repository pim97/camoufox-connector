<?php
/**
 * Camoufox Connector - PHP Example
 *
 * This example demonstrates how to connect to Camoufox from PHP
 * using HTTP requests to interact with the connector API.
 *
 * Prerequisites:
 *   PHP 8.0+ with curl extension
 *
 * Start the connector server first:
 *   camoufox-connector --mode pool --pool-size 3
 *
 * Note: For full Playwright integration, consider using:
 *   https://github.com/nicklockwood/PHPlaywright
 */

$API_URL = getenv('CAMOUFOX_API') ?: 'http://localhost:8080';

/**
 * Make HTTP GET request
 */
function httpGet(string $url): array {
    $ch = curl_init();
    curl_setopt_array($ch, [
        CURLOPT_URL => $url,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => ['Content-Type: application/json'],
        CURLOPT_TIMEOUT => 30,
    ]);
    
    $response = curl_exec($ch);
    $statusCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $error = curl_error($ch);
    curl_close($ch);
    
    if ($error) {
        throw new Exception("HTTP request failed: $error");
    }
    
    return [
        'status' => $statusCode,
        'body' => json_decode($response, true),
    ];
}

/**
 * Get the next available browser endpoint using round-robin
 */
function getNextEndpoint(): string {
    global $API_URL;
    
    try {
        $response = httpGet("$API_URL/next");
        
        if ($response['status'] !== 200) {
            throw new Exception("Failed to get endpoint: HTTP {$response['status']}");
        }
        
        return $response['body']['endpoint'];
    } catch (Exception $e) {
        throw new Exception(
            "Cannot connect to Camoufox Connector at $API_URL.\n" .
            "Please make sure the server is running:\n" .
            "  camoufox-connector --mode pool --pool-size 3\n" .
            "Error: " . $e->getMessage()
        );
    }
}

/**
 * Get all available browser endpoints
 */
function getAllEndpoints(): array {
    global $API_URL;
    
    $response = httpGet("$API_URL/endpoints");
    return $response['body']['endpoints'];
}

/**
 * Check server health
 */
function checkHealth(): bool {
    global $API_URL;
    
    try {
        $response = httpGet("$API_URL/health");
        echo "Server health: " . json_encode($response['body'], JSON_PRETTY_PRINT) . "\n";
        return $response['body']['status'] === 'healthy';
    } catch (Exception $e) {
        echo "❌ Cannot connect to Camoufox Connector at $API_URL\n";
        echo "Please start the server first:\n";
        echo "  camoufox-connector --mode pool --pool-size 3\n\n";
        return false;
    }
}

/**
 * Get pool statistics
 */
function getStats(): array {
    global $API_URL;
    
    $response = httpGet("$API_URL/stats");
    return $response['body'];
}

/**
 * Basic example: Get endpoints and display info
 */
function basicExample(): void {
    echo "\n=== Basic Example ===\n\n";
    
    // Get a browser endpoint using round-robin
    $endpoint = getNextEndpoint();
    echo "Got endpoint: $endpoint\n";
    
    // In a real application, you would connect to this WebSocket endpoint
    // using a Playwright-compatible PHP library or WebSocket client
    echo "\nTo use this endpoint:\n";
    echo "1. Connect to the WebSocket using a compatible client\n";
    echo "2. Send Playwright protocol commands\n";
    echo "3. Receive browser responses\n";
}

/**
 * Pool example: Get multiple endpoints
 */
function poolExample(): void {
    echo "\n=== Pool Example ===\n\n";
    
    // Get multiple endpoints to demonstrate round-robin
    for ($i = 1; $i <= 5; $i++) {
        $endpoint = getNextEndpoint();
        echo "Request $i: $endpoint\n";
    }
}

/**
 * Stats example: Display pool statistics
 */
function statsExample(): void {
    echo "\n=== Stats Example ===\n\n";
    
    $stats = getStats();
    
    echo "Mode: {$stats['mode']}\n";
    echo "Total instances: {$stats['total_instances']}\n";
    echo "Healthy instances: {$stats['healthy_instances']}\n";
    echo "Active connections: {$stats['active_connections']}\n";
    echo "Total connections: {$stats['total_connections']}\n";
}

// Main execution
try {
    // Check if server is healthy
    if (!checkHealth()) {
        echo "Server is not healthy. Please start the connector first.\n";
        exit(1);
    }
    
    // Run examples
    basicExample();
    poolExample();
    statsExample();
    
    echo "\n✓ All examples completed successfully!\n\n";
    
} catch (Exception $e) {
    echo "Error: " . $e->getMessage() . "\n";
    exit(1);
}
