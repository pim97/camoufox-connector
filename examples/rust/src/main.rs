//! Camoufox Connector - Rust Example
//!
//! This example demonstrates how to connect to Camoufox from Rust
//! using HTTP requests to get the WebSocket endpoint.
//!
//! Prerequisites:
//!   cargo add reqwest tokio serde serde_json
//!
//! Start the connector server first:
//!   camoufox-connector --mode pool --pool-size 3
//!
//! Note: Playwright doesn't have an official Rust client, so this example
//! shows how to get the endpoint which you can use with a WebSocket client.

use reqwest::Client;
use serde::Deserialize;
use std::env;

#[derive(Deserialize, Debug)]
struct EndpointResponse {
    endpoint: String,
}

#[derive(Deserialize, Debug)]
struct HealthResponse {
    status: String,
}

#[derive(Deserialize, Debug)]
struct StatsResponse {
    mode: String,
    total_instances: i32,
    healthy_instances: i32,
    active_connections: i32,
    total_connections: i32,
}

fn get_api_url() -> String {
    env::var("CAMOUFOX_API").unwrap_or_else(|_| "http://localhost:8080".to_string())
}

/// Get the next available browser endpoint using round-robin
async fn get_next_endpoint(client: &Client) -> Result<String, Box<dyn std::error::Error>> {
    let api_url = get_api_url();
    let response: EndpointResponse = client
        .get(format!("{}/next", api_url))
        .send()
        .await?
        .json()
        .await?;
    
    Ok(response.endpoint)
}

/// Check server health
async fn check_health(client: &Client) -> Result<bool, Box<dyn std::error::Error>> {
    let api_url = get_api_url();
    let response: HealthResponse = client
        .get(format!("{}/health", api_url))
        .send()
        .await?
        .json()
        .await?;
    
    println!("Server health: {:?}", response);
    Ok(response.status == "healthy")
}

/// Get pool statistics
async fn get_stats(client: &Client) -> Result<StatsResponse, Box<dyn std::error::Error>> {
    let api_url = get_api_url();
    let response: StatsResponse = client
        .get(format!("{}/stats", api_url))
        .send()
        .await?
        .json()
        .await?;
    
    Ok(response)
}

/// Example: Get endpoints for multiple requests (simulating pool usage)
async fn pool_example(client: &Client) -> Result<(), Box<dyn std::error::Error>> {
    println!("\n=== Pool Example ===\n");
    
    // Get multiple endpoints to demonstrate round-robin
    for i in 1..=5 {
        let endpoint = get_next_endpoint(client).await?;
        println!("Request {}: Got endpoint {}", i, endpoint);
        
        // In a real application, you would:
        // 1. Connect to the WebSocket endpoint
        // 2. Use a Playwright-compatible protocol to control the browser
        // 3. Perform your automation tasks
    }
    
    Ok(())
}

/// Example: Get and display stats
async fn stats_example(client: &Client) -> Result<(), Box<dyn std::error::Error>> {
    println!("\n=== Stats Example ===\n");
    
    let stats = get_stats(client).await?;
    
    println!("Mode: {}", stats.mode);
    println!("Total instances: {}", stats.total_instances);
    println!("Healthy instances: {}", stats.healthy_instances);
    println!("Active connections: {}", stats.active_connections);
    println!("Total connections: {}", stats.total_connections);
    
    Ok(())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let client = Client::new();
    let api_url = get_api_url();
    
    // Check if server is healthy
    match check_health(&client).await {
        Ok(true) => println!("Server is healthy!"),
        Ok(false) => {
            eprintln!("Server is not healthy. Please start the connector first.");
            std::process::exit(1);
        }
        Err(e) => {
            eprintln!("Cannot connect to Camoufox Connector at {}", api_url);
            eprintln!("Please start the server first:");
            eprintln!("  camoufox-connector --mode pool --pool-size 3");
            eprintln!("\nError: {}", e);
            std::process::exit(1);
        }
    }
    
    // Run examples
    pool_example(&client).await?;
    stats_example(&client).await?;
    
    println!("\n✓ All examples completed successfully!\n");
    
    // Note: To actually control the browser, you would need to:
    // 1. Connect to the WebSocket endpoint using a WebSocket client (e.g., tungstenite)
    // 2. Implement the Playwright protocol (CDP-like commands)
    // 3. Or use a Rust browser automation library that supports remote connections
    
    println!("Note: This example shows API usage. For full browser automation,");
    println!("connect to the WebSocket endpoint using a compatible client.");
    
    Ok(())
}
