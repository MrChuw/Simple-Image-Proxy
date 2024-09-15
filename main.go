package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
)

func goDeeper(path string, folder map[string]interface{}, wg *sync.WaitGroup) {
	defer wg.Done()

	entries, err := os.ReadDir(path)
	if err != nil {
		fmt.Println(err)
		return
	}

	for _, entry := range entries {
		fullPath := filepath.Join(path, entry.Name())
		if entry.IsDir() {
			if _, exists := folder[entry.Name()]; !exists {
				folder[entry.Name()] = make(map[string]interface{})
			}
			wg.Add(1)
			go goDeeper(fullPath, folder[entry.Name()].(map[string]interface{}), wg)
		} else {
			folder[entry.Name()] = fullPath
		}
	}
}

func generate(dirPath string) (map[string]interface{}, error) {
	info, err := os.Stat(dirPath)
	if err != nil {
		return nil, err
	}

	if !info.IsDir() {
		return map[string]interface{}{filepath.Base(dirPath): dirPath}, nil
	}

	tempState := make(map[string]interface{})
	entries, err := os.ReadDir(dirPath)
	if err != nil {
		return nil, err
	}

	var wg sync.WaitGroup
	for _, entry := range entries {
		fullPath := filepath.Join(dirPath, entry.Name())
		if entry.IsDir() {
			if _, exists := tempState[entry.Name()]; !exists {
				tempState[entry.Name()] = make(map[string]interface{})
			}
			wg.Add(1)
			go goDeeper(fullPath, tempState[entry.Name()].(map[string]interface{}), &wg)
		} else {
			tempState[entry.Name()] = fullPath
		}
	}

	wg.Wait()

	for k, v := range tempState {
		if v == nil {
			delete(tempState, k)
		}
	}

	return tempState, nil
}

func generatePaths(paths []string) (map[string]interface{}, error) {
	result := make(map[string]interface{})
	var wg sync.WaitGroup

	for _, path := range paths {
		wg.Add(1)
		go func(p string) {
			defer wg.Done()
			baseName := filepath.Base(p)
			tempState, err := generate(p)
			if err != nil {
				fmt.Println(err)
				return
			}
			if len(tempState) > 0 {
				result[baseName] = tempState
			}
		}(path)
	}

	wg.Wait()

	return result, nil
}

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: go run main.go <path1> [path2 ...]")
		return
	}

	paths := os.Args[1:]

	result, err := generatePaths(paths)
	if err != nil {
		fmt.Println(err)
		return
	}

	jsonResult, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		fmt.Println(err)
		return
	}

	fmt.Println(string(jsonResult))
}

