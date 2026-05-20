import pickle
import sys

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pickle_to_ply.py <path_to_pickle_file>")
        sys.exit(1)

    pickle_path = sys.argv[1]
    data = pickle.load(open(pickle_path, 'rb'))
    print(f"{pickle_path},{data.shape}")