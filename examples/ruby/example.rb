# Camoufox Connector - Ruby Example
#
# This example demonstrates how to connect to Camoufox from Ruby
# using HTTP requests to interact with the connector API.
#
# Prerequisites:
#   gem install httparty playwright-ruby-client
#
# Start the connector server first:
#   camoufox-connector --mode pool --pool-size 3

require 'net/http'
require 'json'
require 'uri'

API_URL = ENV['CAMOUFOX_API'] || 'http://localhost:8080'

# Get the next available browser endpoint using round-robin
def get_next_endpoint
  uri = URI("#{API_URL}/next")
  response = Net::HTTP.get_response(uri)
  
  unless response.is_a?(Net::HTTPSuccess)
    raise "Failed to get endpoint: #{response.code} #{response.message}"
  end
  
  JSON.parse(response.body)['endpoint']
rescue Errno::ECONNREFUSED, SocketError => e
  raise "Cannot connect to Camoufox Connector at #{API_URL}.\n" \
        "Please make sure the server is running:\n" \
        "  camoufox-connector --mode pool --pool-size 3\n" \
        "Error: #{e.message}"
end

# Get all available browser endpoints
def get_all_endpoints
  uri = URI("#{API_URL}/endpoints")
  response = Net::HTTP.get_response(uri)
  JSON.parse(response.body)['endpoints']
end

# Check server health
def check_health
  uri = URI("#{API_URL}/health")
  response = Net::HTTP.get_response(uri)
  data = JSON.parse(response.body)
  puts "Server health: #{JSON.pretty_generate(data)}"
  data['status'] == 'healthy'
rescue Errno::ECONNREFUSED, SocketError
  puts "❌ Cannot connect to Camoufox Connector at #{API_URL}"
  puts "Please start the server first:"
  puts "  camoufox-connector --mode pool --pool-size 3"
  puts
  false
end

# Get pool statistics
def get_stats
  uri = URI("#{API_URL}/stats")
  response = Net::HTTP.get_response(uri)
  JSON.parse(response.body)
end

# Basic example: Get endpoints and display info
def basic_example
  puts "\n=== Basic Example ===\n\n"
  
  # Get a browser endpoint using round-robin
  endpoint = get_next_endpoint
  puts "Got endpoint: #{endpoint}"
  
  # If using playwright-ruby-client:
  # require 'playwright'
  # Playwright.create(playwright_cli_executable_path: 'npx playwright') do |playwright|
  #   browser = playwright.firefox.connect(endpoint)
  #   page = browser.new_page
  #   page.goto('https://example.com')
  #   puts page.title
  #   browser.close
  # end
  
  puts "\nTo use with Playwright Ruby client:"
  puts "  browser = playwright.firefox.connect('#{endpoint}')"
  puts "  page = browser.new_page"
  puts "  page.goto('https://example.com')"
end

# Pool example: Get multiple endpoints
def pool_example
  puts "\n=== Pool Example ===\n\n"
  
  # Get multiple endpoints to demonstrate round-robin
  5.times do |i|
    endpoint = get_next_endpoint
    puts "Request #{i + 1}: #{endpoint}"
  end
end

# Stats example: Display pool statistics
def stats_example
  puts "\n=== Stats Example ===\n\n"
  
  stats = get_stats
  
  puts "Mode: #{stats['mode']}"
  puts "Total instances: #{stats['total_instances']}"
  puts "Healthy instances: #{stats['healthy_instances']}"
  puts "Active connections: #{stats['active_connections']}"
  puts "Total connections: #{stats['total_connections']}"
end

# Main execution
begin
  # Check if server is healthy
  unless check_health
    puts "Server is not healthy. Please start the connector first."
    exit 1
  end
  
  # Run examples
  basic_example
  pool_example
  stats_example
  
  puts "\n✓ All examples completed successfully!\n\n"
  
rescue StandardError => e
  puts "Error: #{e.message}"
  exit 1
end
