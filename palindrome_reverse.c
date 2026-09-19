#include <stdio.h>
#include <string.h>
#include <ctype.h>
#include <stdlib.h>

// Function to reverse a string
void reverseString(char* str) {
    int length = strlen(str);
    int start = 0;
    int end = length - 1;
    
    while (start < end) {
        char temp = str[start];
        str[start] = str[end];
        str[end] = temp;
        start++;
        end--;
    }
}

// Function to check if a string is a palindrome (case-insensitive)
int isPalindrome(char* str) {
    int length = strlen(str);
    int start = 0;
    int end = length - 1;
    
    while (start < end) {
        // Convert to lowercase for comparison
        if (tolower(str[start]) != tolower(str[end])) {
            return 0; // Not a palindrome
        }
        start++;
        end--;
    }
    return 1; // Is a palindrome
}

// Function to check if a string is a palindrome (ignoring spaces and punctuation)
int isPalindromeIgnoreSpaces(char* str) {
    int length = strlen(str);
    int start = 0;
    int end = length - 1;
    
    while (start < end) {
        // Skip non-alphanumeric characters from the left
        while (start < end && !isalnum(str[start])) {
            start++;
        }
        
        // Skip non-alphanumeric characters from the right
        while (start < end && !isalnum(str[end])) {
            end--;
        }
        
        // Compare characters (case-insensitive)
        if (tolower(str[start]) != tolower(str[end])) {
            return 0; // Not a palindrome
        }
        
        start++;
        end--;
    }
    return 1; // Is a palindrome
}

// Function to create a reversed copy of a string
char* createReversedString(const char* str) {
    int length = strlen(str);
    char* reversed = (char*)malloc((length + 1) * sizeof(char));
    
    if (reversed == NULL) {
        return NULL; // Memory allocation failed
    }
    
    for (int i = 0; i < length; i++) {
        reversed[i] = str[length - 1 - i];
    }
    reversed[length] = '\0';
    
    return reversed;
}

int main() {
    char str1[100];
    char str2[100];
    
    printf("Enter a string to check for palindrome: ");
    fgets(str1, sizeof(str1), stdin);
    
    // Remove newline character if present
    str1[strcspn(str1, "\n")] = '\0';
    
    // Check if it's a palindrome
    if (isPalindrome(str1)) {
        printf("'%s' is a palindrome!\n", str1);
    } else {
        printf("'%s' is not a palindrome.\n", str1);
    }
    
    // Check palindrome ignoring spaces and punctuation
    if (isPalindromeIgnoreSpaces(str1)) {
        printf("'%s' is a palindrome (ignoring spaces/punctuation)!\n", str1);
    } else {
        printf("'%s' is not a palindrome (ignoring spaces/punctuation).\n", str1);
    }
    
    printf("\nEnter a string to reverse: ");
    fgets(str2, sizeof(str2), stdin);
    str2[strcspn(str2, "\n")] = '\0';
    
    // Create a reversed copy
    char* reversed = createReversedString(str2);
    if (reversed != NULL) {
        printf("Original: %s\n", str2);
        printf("Reversed: %s\n", reversed);
        free(reversed);
    }
    
    // Reverse the original string in-place
    reverseString(str2);
    printf("In-place reversed: %s\n", str2);
    
    return 0;
}