import os
import re

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Fetch the user's current balance
    usr_balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    balance = usr_balance[0]['cash']

    current_user_query = db.execute("SELECT username FROM users WHERE id = ?", (session["user_id"],))
    current_user_row = current_user_query[0] if current_user_query else None
    current_user = current_user_row['username'] if current_user_row else None

    # Retrieve stock symbols and quantities for the current user
    user_data_query = db.execute("SELECT stocksym, SUM(quantity) AS total_quantity FROM usr_purchases WHERE buyer_id = ? GROUP BY stocksym", (session["user_id"],))
    user_data = user_data_query if user_data_query else []

    # Create a dictionary to store stock symbols and their corresponding quantities
    qty_dict = {item['stocksym']: item['total_quantity'] for item in user_data}

    # Retrieve current prices for each stock symbol
    prices = {stock['stocksym']: lookup(stock['stocksym'])['price'] for stock in user_data}

    # Calculate the total value of all stocks
    total_stock_value = sum(qty_dict[stock] * prices[stock] for stock in qty_dict)

    stock_values = {stock: qty_dict[stock] * prices[stock] for stock in qty_dict}

    # Calculate the total value of the portfolio
    total_portfolio_value = balance + total_stock_value

    # Render the index.html template with the necessary data
    return render_template("index.html", qty=qty_dict, prices=prices, user=current_user, balance=balance, total_portfolio_value=total_portfolio_value, stock_values=stock_values)






@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":
        # Fetch the user's current balance
        usr_balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        balance = usr_balance[0]['cash']

        # Get the symbol and shares to buy from the form
        symb_purch = request.form.get("symbol").upper()
        shares_buy = request.form.get("shares")

        # Check for empty fields
        if not symb_purch or not shares_buy:
            return apology("No empty fields allowed")

        try:
            shares_buy = int(shares_buy)
            if shares_buy <= 0:
                return apology("Shares must be a positive whole number")
        except ValueError:
            return apology("Invalid number of shares")

        # Lookup the symbol to check its validity
        symb_exist = lookup(symb_purch)
        if symb_exist is None:
            return apology("Invalid symbol")

        # Calculate the total purchase price
        purchase_price = symb_exist['price'] * shares_buy

        # Check if the user has enough funds
        if balance < purchase_price:
            return apology("Not enough funds")

        # Insert the new purchase into usr_purchases table
        db.execute("INSERT INTO usr_purchases (stocksym, quantity, buyer_id) VALUES (?, ?, ?)", symb_purch, shares_buy, session["user_id"])

        # Update the user's balance
        new_balance = balance - purchase_price
        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_balance, session["user_id"])

        # Add the buy transaction to the history
        db.execute("INSERT INTO transactions (user_id, symbol, quantity, price, type) VALUES (?, ?, ?, ?, ?)",
                   session["user_id"], symb_purch, shares_buy, symb_exist['price'], "buy")

        return redirect("/")

    # Fetch the updated balance again after the purchase
    usr_balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    balance = usr_balance[0]['cash']

    return render_template("buy.html", balance=balance)





@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute("SELECT * FROM transactions WHERE user_id = ?", session["user_id"])

    # Render the history.html template with the transaction data
    return render_template("history.html", transactions=transactions)



@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symb = request.form.get("symbol")
        #Check if the symbol is empty
        if not symb:
            return apology("Must enter a valid symbol")
        #Look up for the symbol using the API
        sym = lookup(symb)
        #Check if the symbol is invalid
        if sym is None:
            return apology("Invalid symbol")
        return render_template("quoted.html", sym = sym)
    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        reg_name = request.form.get("username")
        reg_pass = request.form.get("password")
        reg_conf = request.form.get("confirmation")

        # Validate user input
        if not reg_name or not reg_pass or not reg_conf:
            return apology("No empty fields")
        elif reg_pass != reg_conf:
            return apology("Passwords do not match")
        elif not re.match(r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$", reg_pass):
            return apology("Password must contain at least 8 characters with at least one letter, one number, and one special character")

        # Check if the username is already taken
        user_exist = db.execute("SELECT username FROM users WHERE username = ?", reg_name)
        if user_exist:
            return apology("Username already taken")
        else:
            hash_pass = generate_password_hash(reg_pass)
            db.execute("INSERT INTO users(username, hash) VALUES(?, ?)", reg_name, hash_pass)

            # Log in the user after successful registration
            row = db.execute("SELECT id FROM users WHERE username = ?", (reg_name,))
            if row:
                user_id = row[0]['id']
                session["user_id"] = user_id
                return redirect("/")

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # Get the list of stock symbols owned by the user
    stock_list_query = db.execute("SELECT DISTINCT stocksym FROM usr_purchases WHERE buyer_id = ?", session["user_id"])
    STOCKS = [stock['stocksym'] for stock in stock_list_query]

    if request.method == "POST":
        user_stock = request.form.get("symbol")
        shares_num = request.form.get("shares")

        # Get the total quantity of the selected stock owned by the user
        shares_owned_query_result = db.execute("SELECT SUM(quantity) AS total_quantity FROM usr_purchases WHERE buyer_id = ? AND stocksym = ?", session["user_id"], user_stock)

        if shares_owned_query_result:
            shares_owned = shares_owned_query_result[0]['total_quantity']
        else:
            return apology("You don't own any shares of this stock")

        if not user_stock or user_stock not in STOCKS:
            return apology("Not a valid stock")

        if shares_num and int(shares_num) <= shares_owned:
            # Retrieve the current price of the stock
            stock_price = lookup(user_stock)['price']

            # Calculate the total value of the shares being sold
            total_sale_value = int(shares_num) * stock_price

            # Update the user's cash balance
            db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", total_sale_value, session["user_id"])

            # Calculate the new quantity after selling
            new_quantity = max(0, shares_owned - int(shares_num))

            # Update the database with the new quantity
            db.execute("UPDATE usr_purchases SET quantity = ? WHERE buyer_id = ? AND stocksym = ?", new_quantity, session["user_id"], user_stock)

            # Insert the sell transaction into the history
            db.execute("INSERT INTO transactions (user_id, symbol, quantity, price, type) VALUES (?, ?, ?, ?, ?)",
                       session["user_id"], user_stock, int(shares_num), stock_price, "sell")

            # Redirect to the main page after selling
            return redirect("/")
        else:
            return apology("You cannot sell more shares than you own")

    return render_template("sell.html", stocks=STOCKS)










