#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>
#include <process.h> // For multi-threading
#include <ddk/ntdddisk.h>

#define BUFFER_SIZE 1048576 // 1MB buffer for performance
#define MAX_THREADS 16      // Max number of concurrent threads

// --- Structs for Multi-threading ---
typedef struct {
    char filepath[MAX_PATH];
    char method[20];
} WipeFileInfo;

// --- Forward Declarations ---
int wipe_file(const char *filepath, const char *method, int is_part_of_folder);
unsigned __stdcall wipe_file_thread(void *data);

// --- Overwrite Pass Functions ---
void file_overwrite_pass(FILE *f, long long file_size, int pass_num, int total_passes, char pattern) {
    rewind(f);
    char *buffer = (char*)malloc(BUFFER_SIZE);
    long long total_written = 0;
    char pass_desc[50];
    int is_random = 0;

    if (pattern == 0x00) { memset(buffer, 0x00, BUFFER_SIZE); snprintf(pass_desc, 50, "Writing zeros (0x00)..."); } 
    else if (pattern == 0xFF) { memset(buffer, 0xFF, BUFFER_SIZE); snprintf(pass_desc, 50, "Writing ones (0xFF)..."); } 
    else if ((unsigned char)pattern == 0x55) { memset(buffer, 0x55, BUFFER_SIZE); snprintf(pass_desc, 50, "Writing pattern 0x55..."); } 
    else if ((unsigned char)pattern == 0xAA) { memset(buffer, 0xAA, BUFFER_SIZE); snprintf(pass_desc, 50, "Writing pattern 0xAA..."); } 
    else { is_random = 1; snprintf(pass_desc, 50, "Writing random data..."); }
    
    printf("  Pass %d of %d: %s\n", pass_num, total_passes, pass_desc);

    if (is_random) {
        for (size_t i = 0; i < BUFFER_SIZE; i++) buffer[i] = rand() % 256;
    }

    while (total_written < file_size) {
        size_t to_write = BUFFER_SIZE;
        if (file_size - total_written < BUFFER_SIZE) to_write = (size_t)(file_size - total_written);
        fwrite(buffer, 1, to_write, f);
        total_written += to_write;
    }
    fflush(f);
    free(buffer);
}

void disk_overwrite_pass(HANDLE hDevice, unsigned __int64 disk_size, int pass_num, int total_passes, char pattern) {
    char *buffer = (char*)malloc(BUFFER_SIZE);
    unsigned __int64 total_written = 0;
    char pass_desc[50];
    DWORD bytesWritten;
    int is_random = 0;

    if (pattern == 0x00) { memset(buffer, 0x00, BUFFER_SIZE); snprintf(pass_desc, 50, "Writing zeros (0x00)..."); } 
    else if (pattern == 0xFF) { memset(buffer, 0xFF, BUFFER_SIZE); snprintf(pass_desc, 50, "Writing ones (0xFF)..."); } 
    else if ((unsigned char)pattern == 0x55) { memset(buffer, 0x55, BUFFER_SIZE); snprintf(pass_desc, 50, "Writing pattern 0x55..."); } 
    else if ((unsigned char)pattern == 0xAA) { memset(buffer, 0xAA, BUFFER_SIZE); snprintf(pass_desc, 50, "Writing pattern 0xAA..."); } 
    else { is_random = 1; snprintf(pass_desc, 50, "Writing random data..."); }

    printf("Pass %d of %d: %s\n", pass_num, total_passes, pass_desc);
    
    if (is_random) {
        for (size_t i = 0; i < BUFFER_SIZE; i++) buffer[i] = rand() % 256;
    }

    SetFilePointer(hDevice, 0, NULL, FILE_BEGIN);
    while (total_written < disk_size) {
        DWORD amount_to_write = BUFFER_SIZE;
        if (disk_size - total_written < BUFFER_SIZE) amount_to_write = (DWORD)(disk_size - total_written);
        WriteFile(hDevice, buffer, amount_to_write, &bytesWritten, NULL);
        if (bytesWritten == 0) break;
        total_written += bytesWritten;
        printf("\rProgress: %.2f%%", ((double)total_written / disk_size) * 100);
    }
    printf("\rProgress: 100.00%%\n");
    free(buffer);
}

// --- Multi-threaded Folder Wiping ---
int wipe_folder_recursive(const char *basePath, const char *method) {
    WIN32_FIND_DATA findFileData;
    char searchPath[MAX_PATH];
    HANDLE hThreads[MAX_THREADS];
    int thread_count = 0;

    snprintf(searchPath, MAX_PATH, "%s\\*", basePath);
    HANDLE hFind = FindFirstFile(searchPath, &findFileData);
    if (hFind == INVALID_HANDLE_VALUE) return 1;

    do {
        if (strcmp(findFileData.cFileName, ".") != 0 && strcmp(findFileData.cFileName, "..") != 0) {
            char fullPath[MAX_PATH];
            snprintf(fullPath, MAX_PATH, "%s\\%s", basePath, findFileData.cFileName);
            if (findFileData.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
                wipe_folder_recursive(fullPath, method);
            } else {
                WipeFileInfo *info = malloc(sizeof(WipeFileInfo));
                strncpy(info->filepath, fullPath, MAX_PATH);
                strncpy(info->method, method, 20);
                hThreads[thread_count] = (HANDLE)_beginthreadex(NULL, 0, &wipe_file_thread, info, 0, NULL);
                thread_count++;
                if (thread_count == MAX_THREADS) {
                    WaitForMultipleObjects(thread_count, hThreads, TRUE, INFINITE);
                    for (int i = 0; i < thread_count; i++) CloseHandle(hThreads[i]);
                    thread_count = 0;
                }
            }
        }
    } while (FindNextFile(hFind, &findFileData) != 0);
    FindClose(hFind);

    if (thread_count > 0) {
        WaitForMultipleObjects(thread_count, hThreads, TRUE, INFINITE);
        for (int i = 0; i < thread_count; i++) CloseHandle(hThreads[i]);
    }
    
    SetFileAttributes(basePath, FILE_ATTRIBUTE_NORMAL);
    if (RemoveDirectory(basePath)) {
        printf("[Folder] Deleted empty directory: %s\n", basePath);
    } else {
        if (strlen(basePath) > 3) {
             printf("[Folder] Could not delete directory (might be in use): %s\n", basePath);
        }
    }
    return 0;
}

unsigned __stdcall wipe_file_thread(void *data) {
    WipeFileInfo *info = (WipeFileInfo*)data;
    wipe_file(info->filepath, info->method, 1);
    free(info);
    _endthreadex(0);
    return 0;
}

int wipe_file(const char *filepath, const char *method, int is_part_of_folder) {
    if (!is_part_of_folder) {
        printf("Zero Leaks Wiping Engine v0.7\n------------------------------------\nTarget: %s\n------------------------------------\n", filepath);
    } else {
        printf("[File] Wiping: %s\n", filepath);
    }
    
    DWORD attrs = GetFileAttributes(filepath);
    if (attrs != INVALID_FILE_ATTRIBUTES && (attrs & (FILE_ATTRIBUTE_READONLY | FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))) {
        printf("  NOTE: Removing protected attributes from file.\n");
        SetFileAttributes(filepath, FILE_ATTRIBUTE_NORMAL);
    }

    FILE *f = fopen(filepath, "r+b");
    if (!f) { fprintf(stderr, "  ERROR: Cannot open file '%s'. Skipping.\n", filepath); return 1; }

    fseek(f, 0, SEEK_END);
    long long file_size = _ftelli64(f);
    printf("  File size: %lld bytes.\n", file_size);

    if (file_size > 0) {
        if (strcmp(method, "--clear") == 0) { file_overwrite_pass(f, file_size, 1, 1, 0x00); } 
        else if (strcmp(method, "--purge") == 0) { file_overwrite_pass(f, file_size, 1, 3, 0x00); file_overwrite_pass(f, file_size, 2, 3, 0xFF); file_overwrite_pass(f, file_size, 3, 3, 'R'); } 
        else if (strcmp(method, "--destroy-sw") == 0) { file_overwrite_pass(f, file_size, 1, 7, 0x00); file_overwrite_pass(f, file_size, 2, 7, 0xFF); file_overwrite_pass(f, file_size, 3, 7, 'R'); file_overwrite_pass(f, file_size, 4, 7, 0x55); file_overwrite_pass(f, file_size, 5, 7, 0xAA); file_overwrite_pass(f, file_size, 6, 7, 'R'); file_overwrite_pass(f, file_size, 7, 7, 'R'); }
    }

    fclose(f);
    if (remove(filepath) == 0) {
        printf("  SUCCESS: File securely wiped and deleted.\n");
    } else {
        fprintf(stderr, "  ERROR: File overwritten but could not be deleted.\n");
        return 1;
    }
    return 0;
}

int wipe_disk_raw(const char* disk_path, const char* method) {
    printf("Zero Leaks Wiping Engine v0.7\n------------------------------------\nTarget Disk: %s\n------------------------------------\n", disk_path);
    printf("WARNING: This will destroy all data, partitions, and the OS on this disk.\n");

    HANDLE hDevice = CreateFileA(disk_path, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
    if (hDevice == INVALID_HANDLE_VALUE) {
        fprintf(stderr, "ERROR: Could not open disk handle. Ensure you are running as Administrator. LastError=%lu\n", GetLastError());
        return 1;
    }
    
    GET_LENGTH_INFORMATION sizeInfo;
    DWORD bytesReturned;
    if (!DeviceIoControl(hDevice, IOCTL_DISK_GET_LENGTH_INFO, NULL, 0, &sizeInfo, sizeof(sizeInfo), &bytesReturned, NULL)) {
        fprintf(stderr, "ERROR: Could not get disk size. LastError=%lu\n", GetLastError());
        CloseHandle(hDevice);
        return 1;
    }
    
    unsigned __int64 disk_size = sizeInfo.Length.QuadPart;
    printf("Disk size: %.2f GB\n", (double)disk_size / (1024 * 1024 * 1024));

    if (strcmp(method, "--clear") == 0) { disk_overwrite_pass(hDevice, disk_size, 1, 1, 0x00); } 
    else if (strcmp(method, "--purge") == 0) { disk_overwrite_pass(hDevice, disk_size, 1, 3, 0x00); disk_overwrite_pass(hDevice, disk_size, 2, 3, 0xFF); disk_overwrite_pass(hDevice, disk_size, 3, 3, 'R'); } 
    else if (strcmp(method, "--destroy-sw") == 0) { disk_overwrite_pass(hDevice, disk_size, 1, 7, 0x00); disk_overwrite_pass(hDevice, disk_size, 2, 7, 0xFF); disk_overwrite_pass(hDevice, disk_size, 3, 7, 'R'); disk_overwrite_pass(hDevice, disk_size, 4, 7, 0x55); disk_overwrite_pass(hDevice, disk_size, 5, 7, 0xAA); disk_overwrite_pass(hDevice, disk_size, 6, 7, 'R'); disk_overwrite_pass(hDevice, disk_size, 7, 7, 'R'); }
    
    CloseHandle(hDevice);
    printf("SUCCESS: Disk securely wiped.\n");
    return 0;
}

int main(int argc, char *argv[]) {
    if (argc != 4) {
        fprintf(stderr, "Usage: %s <--file|--folder|--disk> <\"path\"> <method>\n", argv[0]);
        return 1;
    }
    char *type = argv[1];
    char *path = argv[2];
    char *method = argv[3];
    srand((unsigned int)time(NULL));
    if (strcmp(type, "--file") == 0) { return wipe_file(path, method, 0); } 
    else if (strcmp(type, "--folder") == 0) { printf("Zero Leaks Wiping Engine v0.7\n------------------------------------\nTarget Folder: %s\n------------------------------------\n", path); return wipe_folder_recursive(path, method); } 
    else if (strcmp(type, "--disk") == 0) { return wipe_disk_raw(path, method); } 
    else { fprintf(stderr, "ERROR: Invalid type specified. Use --file, --folder, or --disk.\n"); return 1; }
    return 0;
}