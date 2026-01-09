/**
 * Camoufox Connector - Kotlin Example
 *
 * This example demonstrates how to connect to Camoufox from Kotlin
 * using the Playwright Java library.
 *
 * Prerequisites:
 *   Add to build.gradle.kts:
 *   implementation("com.microsoft.playwright:playwright:1.44.0")
 *   implementation("com.google.code.gson:gson:2.10.1")
 *
 * Start the connector server first:
 *   camoufox-connector --mode pool --pool-size 3
 */

import com.microsoft.playwright.Playwright
import com.microsoft.playwright.Page
import com.google.gson.Gson
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.nio.file.Paths

val API_URL = System.getenv("CAMOUFOX_API") ?: "http://localhost:8080"
val httpClient: HttpClient = HttpClient.newHttpClient()
val gson = Gson()

data class EndpointResponse(val endpoint: String)
data class HealthResponse(val status: String)
data class StatsResponse(
    val mode: String,
    val total_instances: Int,
    val healthy_instances: Int,
    val active_connections: Int,
    val total_connections: Int
)

/**
 * Get the next available browser endpoint using round-robin
 */
fun getNextEndpoint(): String {
    val request = HttpRequest.newBuilder()
        .uri(URI.create("$API_URL/next"))
        .GET()
        .build()
    
    val response = httpClient.send(request, HttpResponse.BodyHandlers.ofString())
    
    if (response.statusCode() != 200) {
        throw RuntimeException("Failed to get endpoint: ${response.statusCode()}")
    }
    
    return gson.fromJson(response.body(), EndpointResponse::class.java).endpoint
}

/**
 * Check server health
 */
fun checkHealth(): Boolean {
    return try {
        val request = HttpRequest.newBuilder()
            .uri(URI.create("$API_URL/health"))
            .GET()
            .build()
        
        val response = httpClient.send(request, HttpResponse.BodyHandlers.ofString())
        println("Server health: ${response.body()}")
        
        val data = gson.fromJson(response.body(), HealthResponse::class.java)
        data.status == "healthy"
    } catch (e: Exception) {
        println("❌ Cannot connect to Camoufox Connector at $API_URL")
        println("Please start the server first:")
        println("  camoufox-connector --mode pool --pool-size 3")
        false
    }
}

/**
 * Get pool statistics
 */
fun getStats(): StatsResponse {
    val request = HttpRequest.newBuilder()
        .uri(URI.create("$API_URL/stats"))
        .GET()
        .build()
    
    val response = httpClient.send(request, HttpResponse.BodyHandlers.ofString())
    return gson.fromJson(response.body(), StatsResponse::class.java)
}

/**
 * Basic example: Connect and navigate to a page
 */
fun basicExample() {
    println("\n=== Basic Example ===\n")
    
    // Get a browser endpoint using round-robin
    val endpoint = getNextEndpoint()
    println("Connecting to: $endpoint")
    
    Playwright.create().use { playwright ->
        // Connect to Camoufox via WebSocket
        val browser = playwright.firefox().connect(endpoint)
        
        try {
            // Create a new page
            val page = browser.newPage()
            
            // Navigate to a test page
            page.navigate("https://httpbin.org/headers")
            
            // Get page content
            val content = page.textContent("body")
            println("Response: $content")
            
            // Take a screenshot
            page.screenshot(Page.ScreenshotOptions().setPath(Paths.get("screenshot.png")))
            println("Screenshot saved to screenshot.png")
            
        } finally {
            browser.close()
        }
    }
}

/**
 * Pool example: Get multiple endpoints
 */
fun poolExample() {
    println("\n=== Pool Example ===\n")
    
    // Get multiple endpoints to demonstrate round-robin
    repeat(5) { i ->
        val endpoint = getNextEndpoint()
        println("Request ${i + 1}: $endpoint")
    }
}

/**
 * Stats example: Display pool statistics
 */
fun statsExample() {
    println("\n=== Stats Example ===\n")
    
    val stats = getStats()
    
    println("Mode: ${stats.mode}")
    println("Total instances: ${stats.total_instances}")
    println("Healthy instances: ${stats.healthy_instances}")
    println("Active connections: ${stats.active_connections}")
    println("Total connections: ${stats.total_connections}")
}

fun main() {
    try {
        // Check if server is healthy
        if (!checkHealth()) {
            System.err.println("Server is not healthy. Please start the connector first.")
            System.exit(1)
        }
        
        // Run examples
        basicExample()
        poolExample()
        statsExample()
        
        println("\n✓ All examples completed successfully!\n")
        
    } catch (e: Exception) {
        System.err.println("Error: ${e.message}")
        e.printStackTrace()
        System.exit(1)
    }
}
