/**
 * Camoufox Connector - Java Example
 *
 * This example demonstrates how to connect to Camoufox from Java
 * using the Playwright Java library.
 *
 * Prerequisites:
 *   Add to pom.xml:
 *   <dependency>
 *     <groupId>com.microsoft.playwright</groupId>
 *     <artifactId>playwright</artifactId>
 *     <version>1.44.0</version>
 *   </dependency>
 *
 * Start the connector server first:
 *   camoufox-connector --mode pool --pool-size 3
 */

import com.microsoft.playwright.*;
import java.net.http.*;
import java.net.URI;
import com.google.gson.Gson;

public class Example {
    
    private static final String API_URL = System.getenv("CAMOUFOX_API") != null 
        ? System.getenv("CAMOUFOX_API") 
        : "http://localhost:8080";
    
    private static final HttpClient httpClient = HttpClient.newHttpClient();
    private static final Gson gson = new Gson();
    
    static class EndpointResponse {
        String endpoint;
    }
    
    static class HealthResponse {
        String status;
    }
    
    /**
     * Get the next available browser endpoint using round-robin
     */
    public static String getNextEndpoint() throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(API_URL + "/next"))
            .GET()
            .build();
            
        HttpResponse<String> response = httpClient.send(request, 
            HttpResponse.BodyHandlers.ofString());
            
        if (response.statusCode() != 200) {
            throw new RuntimeException("Failed to get endpoint: " + response.statusCode());
        }
        
        EndpointResponse data = gson.fromJson(response.body(), EndpointResponse.class);
        return data.endpoint;
    }
    
    /**
     * Check server health
     */
    public static boolean checkHealth() throws Exception {
        try {
            HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(API_URL + "/health"))
                .GET()
                .build();
                
            HttpResponse<String> response = httpClient.send(request, 
                HttpResponse.BodyHandlers.ofString());
                
            HealthResponse data = gson.fromJson(response.body(), HealthResponse.class);
            System.out.println("Server health: " + response.body());
            return "healthy".equals(data.status);
        } catch (Exception e) {
            System.err.println("Cannot connect to Camoufox Connector at " + API_URL);
            System.err.println("Please start the server first:");
            System.err.println("  camoufox-connector --mode pool --pool-size 3");
            return false;
        }
    }
    
    /**
     * Basic example: Connect and navigate to a page
     */
    public static void basicExample() throws Exception {
        System.out.println("\n=== Basic Example ===\n");
        
        // Get a browser endpoint using round-robin
        String endpoint = getNextEndpoint();
        System.out.println("Connecting to: " + endpoint);
        
        try (Playwright playwright = Playwright.create()) {
            // Connect to Camoufox via WebSocket
            Browser browser = playwright.firefox().connect(endpoint);
            
            try {
                // Create a new page
                Page page = browser.newPage();
                
                // Navigate to a test page
                page.navigate("https://httpbin.org/headers");
                
                // Get page content
                String content = page.textContent("body");
                System.out.println("Response: " + content);
                
                // Take a screenshot
                page.screenshot(new Page.ScreenshotOptions().setPath(
                    java.nio.file.Paths.get("screenshot.png")));
                System.out.println("Screenshot saved to screenshot.png");
                
            } finally {
                browser.close();
            }
        }
    }
    
    public static void main(String[] args) {
        try {
            // Check if server is healthy
            if (!checkHealth()) {
                System.err.println("Server is not healthy. Please start the connector first.");
                System.exit(1);
            }
            
            // Run example
            basicExample();
            
            System.out.println("\n✓ Example completed successfully!\n");
            
        } catch (Exception e) {
            System.err.println("Error: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        }
    }
}
