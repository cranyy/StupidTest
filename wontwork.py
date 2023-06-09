import datetime as dt
import pandas as pd
import yfinance as yf
import requests
import torch
from torch.utils.data import DataLoader
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error
import ta
from keras.models import Sequential
from keras.layers import Dense
from tqdm import tqdm
from bs4 import BeautifulSoup
import re
import json
from transformers import pipeline
from torch import nn
import torch.optim as optim

url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
start = dt.datetime(2020, 1, 1)
end = dt.datetime.now()


# Snippet 1 (Sentiment analysis function) - Place this snippet after the import statements
def get_sentiment_scores(tickers):
    sentiment_analysis = pipeline("sentiment-analysis")
    sentiment_scores = {}

    for ticker in tickers:
        try:
            search_url = f'https://api.cnbc.com/api/search/cnbc/feeds/rs/search?tickers={ticker}&pageSize=10'
            response = requests.get(search_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            data = json.loads(soup.text)

            articles = data['searchResult']['content']['content']['items']
            article_summaries = [re.sub('<[^<]+?>', '', article['summary']) for article in articles]
            scores = [sentiment_analysis(summary)[0]['score'] for summary in article_summaries]

            sentiment_scores[ticker] = sum(scores) / len(scores)
        except Exception as e:
            print(f"Error processing {ticker}: {e}")
            sentiment_scores[ticker] = 0

    return sentiment_scores

# Snippet 2 (Neural network class and training loop) - Place this snippet after the 'neural_network_model' function definition
class StockDataset(torch.utils.data.Dataset):
    def __init__(self, stock_data, lookback):
        self.stock_data = stock_data.dropna()
        self.lookback = lookback

    def __len__(self):
        return len(self.stock_data) - self.lookback

    def __getitem__(self, idx):
        x = self.stock_data.iloc[idx:idx+self.lookback].values
        y = self.stock_data.iloc[idx+self.lookback]['Close']
        return torch.tensor(x, dtype=torch.float32), torch.tensor(y, dtype=torch.float32)

class Predictor(nn.Module):
    def __init__(self, input_size):
        super(Predictor, self).__init__()
        self.linear1 = nn.Linear(input_size, 64)
        self.linear2 = nn.Linear(64, 1)

    def forward(self, x):
        x = torch.relu(self.linear1(x))
        x = self.linear2(x)
        return x

# Add sentiment scores to stock_data
sentiment_scores = get_sentiment_scores(sp500_list)
for symbol, stock_data in historical_data.items():
    if symbol in sentiment_scores:
        stock_data['Sentiment'] = sentiment_scores[symbol]

def neural_network_model(stock_data):
    stock_data = stock_data.dropna()
    X = stock_data[['7_day_mean', '30_day_mean', '365_day_mean', 'RSI', 'MACD', 'MACD_Signal', 'Bollinger_High', 'Bollinger_Low', 'Sentiment']]
    y = stock_data['Close']
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    scaler = MinMaxScaler()
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.transform(X_test)

    lookback = 30
    train_dataset = StockDataset(pd.DataFrame(X_train, columns=X.columns), lookback)
    test_dataset = StockDataset(pd.DataFrame(X_test, columns=X.columns), lookback)
    dataloader = DataLoader(train_dataset, batch_size=32, shuffle=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = Predictor(lookback * X_train.shape[1]).to(device)
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)

    # Training loop
    num_epochs = 100
    for epoch in range(num_epochs):
        model.train()
        running_loss = 0.0
        for inputs, labels in dataloader:
            inputs, labels = inputs.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs.squeeze(), labels)
            loss.backward()
            optimizer.step()
            running_loss += loss.item()
        print(f"Epoch {epoch+1}/{num_epochs}, Loss: {running_loss/len(dataloader)}")

    model.eval()
    with torch.no_grad():
        y_pred = model(torch.tensor(X_test, dtype=torch.float32).to(device)).cpu().numpy()
    mse = mean_squared_error(y_test, y_pred)

    last_30_days = stock_data[['7_day_mean', '30_day_mean', '365_day_mean', 'RSI', 'MACD', 'MACD_Signal', 'Bollinger_High', 'Bollinger_Low', 'Sentiment']].tail(30)
    last_30_days_scaled = scaler.transform(last_30_days)
    future_prices = model(torch.tensor(last_30_days_scaled, dtype=torch.float32).to(device)).cpu().numpy()
    return mse, future_prices

def linear_regression_model(stock_data):
    stock_data = stock_data.dropna()
    X = stock_data[['7_day_mean', '30_day_mean', '365_day_mean']]
    y = stock_data['Close']
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    scaler = MinMaxScaler()
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.transform(X_test)
    model = LinearRegression()
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    mse = mean_squared_error(y_test, y_pred)
    last_30_days = stock_data[['7_day_mean', '30_day_mean', '365_day_mean']].tail(30)
    last_30_days_scaled = scaler.transform(last_30_days)
    future_prices = model.predict(last_30_days_scaled)
    return mse, future_prices

def add_RSI(stock_data, window=14):
    delta = stock_data['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    stock_data['RSI'] = rsi
    return stock_data

def add_MACD(stock_data, short_window=12, long_window=26, signal_window=9):
    short_ema = stock_data['Close'].ewm(span=short_window, adjust=False).mean()
    long_ema = stock_data['Close'].ewm(span=long_window, adjust=False).mean()
    macd = short_ema - long_ema
    macd_signal = macd.ewm(span=signal_window, adjust=False).mean()
    stock_data['MACD'] = macd
    stock_data['MACD_Signal'] = macd_signal
    return stock_data

def add_Bollinger_Bands(stock_data, window=20, num_std=2):
    sma = stock_data['Close'].rolling(window=window).mean()
    std_dev = stock_data['Close'].rolling(window=window).std()
    bollinger_high = sma + (num_std * std_dev)
    bollinger_low = sma - (num_std * std_dev)
    stock_data['Bollinger_High'] = bollinger_high
    stock_data['Bollinger_Low'] = bollinger_low
    return stock_data

def add_sentiment(stock_data, sentiment_data):
    sentiment_data = sentiment_data.resample('D').mean().fillna(method='ffill')
    stock_data = stock_data.merge(sentiment_data, left_index=True, right_index=True, how='left')
    stock_data['Sentiment'] = stock_data['Sentiment'].fillna(method='ffill')
    return stock_data

# Retrieve S&P 500 stock tickers from Wikipedia
wiki_table = pd.read_html(url)[0]
sp500_list = wiki_table['Symbol'].tolist()[:10]

mse_df = pd.DataFrame(columns=['Symbol', 'LR_MSE', 'NN_MSE', '1d_Action_NN', '7d_Action_NN', '1month_Action_NN',
                               '1d_Action_LR', '7d_Action_LR', '1month_Action_LR'])

for symbol in tqdm(sp500_list):
    try:
        # Get stock data
        stock_data = get_stock_data(symbol, start, end)

        # Add features to the stock data
        stock_data = add_features(stock_data)

        # Get sentiment data for the stock
        sentiment_data = get_sentiment_data(symbol)

        # Add sentiment data to the stock data
        stock_data = add_sentiment(stock_data, sentiment_data)

        # Train and evaluate the neural network model
        nn_mse, nn_future_prices, nn_actions = neural_network_model(stock_data)

        # Train and evaluate the linear regression model
        lr_mse, lr_future_prices, lr_actions = linear_regression_model(stock_data)

        # Save the results to the mse_df DataFrame
        new_row = pd.DataFrame({
            'Symbol': [symbol],
            'LR_MSE': [lr_mse],
            'NN_MSE': [nn_mse],
            '1d_Action_NN': [nn_actions[0]],
            '7d_Action_NN': [nn_actions[1]],
            '1month_Action_NN': [nn_actions[2]],
            '1d_Action_LR': [lr_actions[0]],
            '7d_Action_LR': [lr_actions[1]],
            '1month_Action_LR': [lr_actions[2]]
        })

        mse_df = mse_df.append(new_row, ignore_index=True)
    except Exception as e:
        print(f"Error processing {symbol}: {e}")

# Save the mse_df DataFrame to a CSV file
mse_df.to_csv('mse_comparison.csv', index=False)
print("Analysis completed and saved to mse_comparison.csv")

