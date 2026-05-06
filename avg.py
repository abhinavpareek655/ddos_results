import sys
import argparse
import pandas as pd


def load_dat(path):
    df = pd.read_csv(path, sep="\t")
    df.columns = df.columns.str.strip()
    df["ts"] = pd.to_datetime(df["starttime"], format="%a %b %d %H:%M:%S %Y")
    df = df.sort_values("ts").reset_index(drop=True)
    t0 = df["ts"].iloc[0]; t1 = df["ts"].iloc[-1]
    span = (t1 - t0).total_seconds()
    df["rel"] = 0.0 if span == 0 else (df["ts"] - t0).dt.total_seconds() / span
    return df, t0, t1


def average_ttime(path):
    df, _, _ = load_dat(path)
    if "ttime" not in df.columns:
        raise KeyError("ttime column not found in file")
    ttime = pd.to_numeric(df["ttime"], errors="coerce").dropna()
    if ttime.empty:
        raise ValueError("no numeric ttime values found")
    return ttime.mean()


def main():
    p = argparse.ArgumentParser(description="Compute average of ttime in .dat file")
    p.add_argument("path", help="path to .dat file")
    args = p.parse_args()
    try:
        avg = average_ttime(args.path)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)
    print(f"average_ttime: {avg}")


if __name__ == "__main__":
    main()
