#!/usr/bin/env python3

import subprocess
from urllib.parse import quote
from typing import Optional

class XCallbackURLHandler:
    """Handles x-callback-url execution on macOS systems."""
    
    @staticmethod
    def call_url(url: str) -> str:
        """
        Executes an x-callback-url on macOS using the 'open' command.
        
        Args:
            url: The x-callback-url to execute (must be properly formatted)
            
        Returns:
            The response from the application (if any)
            
        Raises:
            subprocess.CalledProcessError: If the URL execution fails
            RuntimeError: If not running on macOS
        """
        try:
            # Encode the URL to handle special characters
            encoded_url = quote(url, safe=':/?=&')
            
            # Execute the URL using the macOS 'open' command
            result = subprocess.run(
                ['open', encoded_url],
                check=True,
                capture_output=True,
                text=True
            )
            
            return result.stdout
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to execute x-callback-url: {e}")

def test_things_url():
    """Test Things 3 x-callback-url integration."""
    handler = XCallbackURLHandler()
    
    # Test creating a new todo in Things
    url = "things:///add?title=Test%20Todo&notes=Created%20via%20x-callback"
    print(f"Testing URL: {url}")
    response = handler.call_url(url)
    print(f"Response: {response}")

def test_agenda_url():
    """Test Agenda x-callback-url integration."""
    handler = XCallbackURLHandler()
    
    # Test creating a new note in Agenda
    url = "agenda://x-callback-url/create-note?title=Foobar&text=Test%20Note&project-title=Illumio"
    print(f"Testing URL: {url}")
    response = handler.call_url(url)
    print(f"Response: {response}")

if __name__ == "__main__":
    print("Testing x-callback-url functionality...")
    
    while True:
        print("\nChoose a test:")
        print("1. Test Things 3 integration")
        print("2. Test Agenda integration")
        print("3. Enter custom URL")
        print("4. Exit")
        
        choice = input("\nEnter your choice (1-4): ")
        
        if choice == "1":
            test_things_url()
        elif choice == "2":
            test_agenda_url()
        elif choice == "3":
            custom_url = input("Enter x-callback URL to test: ")
            handler = XCallbackURLHandler()
            try:
                response = handler.call_url(custom_url)
                print(f"Response: {response}")
            except Exception as e:
                print(f"Error: {e}")
        elif choice == "4":
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please try again.")
