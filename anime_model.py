import pandas as pd

class AnimeRecommender:

    def __init__(self, csv_file):
        self.df = pd.read_csv(csv_file)
        self.df = self.df.fillna("")
    def get_anime_by_id(self, anime_id):

        anime = self.df[self.df['anime_id'] == anime_id]

        if not anime.empty:
            return anime.iloc[0].to_dict()

        return None

    def get_all_genres(self):
        genres = set()
        for g in self.df['genres']:
            for item in str(g).split(','):
                genres.add(item.strip())
        return sorted(list(genres))

    def get_all_types(self):
        return sorted(self.df['type'].unique())

    def get_top_anime(self, limit=12):
        return self.df.sort_values("score", ascending=False).head(limit).to_dict(orient="records")

    def get_by_id(self, anime_id):
        row = self.df[self.df["anime_id"] == anime_id]
        if row.empty:
            return None
        return row.iloc[0].to_dict()

    def recommend(self, search=None, genre=None, anime_type=None, min_score=0):

        df = self.df

        if search:
            df = df[df['name'].str.contains(search, case=False, na=False)]

        if genre and genre != "All":
            df = df[df['genres'].str.contains(genre, na=False)]

        if anime_type and anime_type != "All":
            df = df[df['type'] == anime_type]

        if min_score:
            df = df[df['score'] >= float(min_score)]

        return df.to_dict(orient="records")