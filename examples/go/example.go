// Camoufox Connector - Go Example
//
// This example demonstrates how to connect to Camoufox from Go
// using the playwright-go library.
//
// Prerequisites:
//   go get github.com/playwright-community/playwright-go
//
// Start the connector server first:
//   camoufox-connector --mode pool --pool-size 3

package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"sync"

	"github.com/playwright-community/playwright-go"
)

var apiURL = getEnvOrDefault("CAMOUFOX_API", "http://localhost:8080")

func getEnvOrDefault(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

// EndpointResponse represents the /next API response
type EndpointResponse struct {
	Endpoint string `json:"endpoint"`
}

// EndpointsResponse represents the /endpoints API response
type EndpointsResponse struct {
	Endpoints []string `json:"endpoints"`
	Count     int      `json:"count"`
}

// HealthResponse represents the /health API response
type HealthResponse struct {
	Status string `json:"status"`
}

// getNextEndpoint fetches the next available browser endpoint using round-robin
func getNextEndpoint() (string, error) {
	resp, err := http.Get(apiURL + "/next")
	if err != nil {
		return "", fmt.Errorf("failed to get endpoint: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("server error: %s", string(body))
	}

	var data EndpointResponse
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return "", fmt.Errorf("failed to decode response: %w", err)
	}

	return data.Endpoint, nil
}

// getAllEndpoints fetches all available browser endpoints
func getAllEndpoints() ([]string, error) {
	resp, err := http.Get(apiURL + "/endpoints")
	if err != nil {
		return nil, fmt.Errorf("failed to get endpoints: %w", err)
	}
	defer resp.Body.Close()

	var data EndpointsResponse
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return data.Endpoints, nil
}

// checkHealth verifies the server is healthy
func checkHealth() (bool, error) {
	resp, err := http.Get(apiURL + "/health")
	if err != nil {
		return false, fmt.Errorf("health check failed: %w", err)
	}
	defer resp.Body.Close()

	var data HealthResponse
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return false, fmt.Errorf("failed to decode response: %w", err)
	}

	return data.Status == "healthy", nil
}

// basicExample demonstrates basic connection and navigation
func basicExample(pw *playwright.Playwright) error {
	fmt.Println("\n=== Basic Example ===\n")

	// Get a browser endpoint using round-robin
	endpoint, err := getNextEndpoint()
	if err != nil {
		return err
	}
	fmt.Printf("Connecting to: %s\n", endpoint)

	// Connect to Camoufox via WebSocket
	browser, err := pw.Firefox.Connect(endpoint)
	if err != nil {
		return fmt.Errorf("failed to connect: %w", err)
	}
	defer browser.Close()

	// Create a new page
	page, err := browser.NewPage()
	if err != nil {
		return fmt.Errorf("failed to create page: %w", err)
	}

	// Navigate to a test page
	_, err = page.Goto("https://httpbin.org/headers")
	if err != nil {
		return fmt.Errorf("failed to navigate: %w", err)
	}

	// Get page content
	content, err := page.TextContent("body")
	if err != nil {
		return fmt.Errorf("failed to get content: %w", err)
	}
	fmt.Printf("Response: %s\n", content)

	// Take a screenshot
	_, err = page.Screenshot(playwright.PageScreenshotOptions{
		Path: playwright.String("screenshot.png"),
	})
	if err != nil {
		return fmt.Errorf("failed to screenshot: %w", err)
	}
	fmt.Println("Screenshot saved to screenshot.png")

	return nil
}

// poolExample demonstrates distributing work across multiple browsers
func poolExample(pw *playwright.Playwright) error {
	fmt.Println("\n=== Pool Example ===\n")

	urls := []string{
		"https://httpbin.org/ip",
		"https://httpbin.org/user-agent",
		"https://httpbin.org/headers",
		"https://httpbin.org/get",
		"https://httpbin.org/cookies",
	}

	type result struct {
		URL     string
		Content string
		Error   error
	}

	results := make(chan result, len(urls))
	var wg sync.WaitGroup

	for _, url := range urls {
		wg.Add(1)
		go func(url string) {
			defer wg.Done()

			// Each call gets the next browser in rotation
			endpoint, err := getNextEndpoint()
			if err != nil {
				results <- result{URL: url, Error: err}
				return
			}
			fmt.Printf("Processing %s via %s\n", url, endpoint)

			browser, err := pw.Firefox.Connect(endpoint)
			if err != nil {
				results <- result{URL: url, Error: err}
				return
			}
			defer browser.Close()

			page, err := browser.NewPage()
			if err != nil {
				results <- result{URL: url, Error: err}
				return
			}

			_, err = page.Goto(url)
			if err != nil {
				results <- result{URL: url, Error: err}
				return
			}

			content, err := page.TextContent("body")
			if err != nil {
				results <- result{URL: url, Error: err}
				return
			}

			// Truncate content
			if len(content) > 100 {
				content = content[:100] + "..."
			}

			results <- result{URL: url, Content: content}
		}(url)
	}

	wg.Wait()
	close(results)

	fmt.Println("\nResults:")
	for r := range results {
		if r.Error != nil {
			fmt.Printf("  %s: ERROR - %v\n", r.URL, r.Error)
		} else {
			fmt.Printf("  %s: %s\n", r.URL, r.Content)
		}
	}

	return nil
}

func main() {
	// Check if server is healthy
	healthy, err := checkHealth()
	if err != nil {
		log.Fatalf("Health check failed: %v", err)
	}
	if !healthy {
		log.Fatal("Server is not healthy. Please start the connector first.")
	}

	// Install Playwright if needed
	err = playwright.Install(&playwright.RunOptions{
		Browsers: []string{"firefox"},
	})
	if err != nil {
		log.Fatalf("Failed to install Playwright: %v", err)
	}

	// Start Playwright
	pw, err := playwright.Run()
	if err != nil {
		log.Fatalf("Failed to start Playwright: %v", err)
	}
	defer pw.Stop()

	// Run examples
	if err := basicExample(pw); err != nil {
		log.Printf("Basic example error: %v", err)
	}

	if err := poolExample(pw); err != nil {
		log.Printf("Pool example error: %v", err)
	}

	fmt.Println("\n✓ All examples completed!\n")
}
