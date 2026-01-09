/**
 * Camoufox Connector - C# (.NET) Example
 *
 * This example demonstrates how to connect to Camoufox from C#
 * using the Playwright .NET library.
 *
 * Prerequisites:
 *   dotnet add package Microsoft.Playwright
 *
 * Start the connector server first:
 *   camoufox-connector --mode pool --pool-size 3
 */

using System;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Playwright;

class Program
{
    private static readonly string ApiUrl = Environment.GetEnvironmentVariable("CAMOUFOX_API") 
        ?? "http://localhost:8080";
    
    private static readonly HttpClient httpClient = new HttpClient();

    record EndpointResponse(string endpoint);
    record HealthResponse(string status);

    /// <summary>
    /// Get the next available browser endpoint using round-robin
    /// </summary>
    static async Task<string> GetNextEndpoint()
    {
        var response = await httpClient.GetStringAsync($"{ApiUrl}/next");
        var data = JsonSerializer.Deserialize<EndpointResponse>(response);
        return data?.endpoint ?? throw new Exception("Failed to get endpoint");
    }

    /// <summary>
    /// Check server health
    /// </summary>
    static async Task<bool> CheckHealth()
    {
        try
        {
            var response = await httpClient.GetStringAsync($"{ApiUrl}/health");
            Console.WriteLine($"Server health: {response}");
            var data = JsonSerializer.Deserialize<HealthResponse>(response);
            return data?.status == "healthy";
        }
        catch (Exception)
        {
            Console.Error.WriteLine($"\n❌ Cannot connect to Camoufox Connector at {ApiUrl}");
            Console.Error.WriteLine("Please start the server first:");
            Console.Error.WriteLine("  camoufox-connector --mode pool --pool-size 3\n");
            return false;
        }
    }

    /// <summary>
    /// Basic example: Connect and navigate to a page
    /// </summary>
    static async Task BasicExample()
    {
        Console.WriteLine("\n=== Basic Example ===\n");

        // Get a browser endpoint using round-robin
        var endpoint = await GetNextEndpoint();
        Console.WriteLine($"Connecting to: {endpoint}");

        // Create Playwright instance
        using var playwright = await Playwright.CreateAsync();
        
        // Connect to Camoufox via WebSocket
        await using var browser = await playwright.Firefox.ConnectAsync(endpoint);

        // Create a new page
        var page = await browser.NewPageAsync();

        // Navigate to a test page
        await page.GotoAsync("https://httpbin.org/headers");

        // Get page content
        var content = await page.TextContentAsync("body");
        Console.WriteLine($"Response: {content}");

        // Take a screenshot
        await page.ScreenshotAsync(new PageScreenshotOptions { Path = "screenshot.png" });
        Console.WriteLine("Screenshot saved to screenshot.png");
    }

    /// <summary>
    /// Pool example: Distribute work across multiple browsers
    /// </summary>
    static async Task PoolExample()
    {
        Console.WriteLine("\n=== Pool Example ===\n");

        var urls = new[]
        {
            "https://httpbin.org/ip",
            "https://httpbin.org/user-agent",
            "https://httpbin.org/headers",
        };

        using var playwright = await Playwright.CreateAsync();

        var tasks = urls.Select(async url =>
        {
            // Each call gets the next browser in rotation
            var endpoint = await GetNextEndpoint();
            Console.WriteLine($"Processing {url} via {endpoint}");

            await using var browser = await playwright.Firefox.ConnectAsync(endpoint);
            var page = await browser.NewPageAsync();
            await page.GotoAsync(url);

            var content = await page.TextContentAsync("body");
            return new { Url = url, Content = content?[..Math.Min(100, content.Length)] + "..." };
        });

        var results = await Task.WhenAll(tasks);

        Console.WriteLine("\nResults:");
        foreach (var result in results)
        {
            Console.WriteLine($"  {result.Url}: {result.Content}");
        }
    }

    static async Task Main(string[] args)
    {
        try
        {
            // Check if server is healthy
            if (!await CheckHealth())
            {
                Console.Error.WriteLine("Server is not healthy. Please start the connector first.");
                Environment.Exit(1);
            }

            // Run examples
            await BasicExample();
            await PoolExample();

            Console.WriteLine("\n✓ All examples completed successfully!\n");
        }
        catch (Exception e)
        {
            Console.Error.WriteLine($"Error: {e.Message}");
            Environment.Exit(1);
        }
    }
}
