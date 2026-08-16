from flask_wtf.csrf import CSRFProtect
import io
import qrcode
import uuid
import os
import requests

from flask import Flask, render_template, redirect, url_for, request, flash, send_file
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user
)
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from models import db, User, Customer, Visit, Reward, AuditLog

# =========================================
# FLASK APPLICATION
# =========================================

app = Flask(__name__)
app.config.from_object(Config)

csrf = CSRFProtect(app)

db.init_app(app)


# =========================================
# FLASK LOGIN
# =========================================

login_manager = LoginManager()
login_manager.init_app(app)

login_manager.login_view = "login"
login_manager.login_message = "Please login to continue."
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
def admin_required():
    return current_user.is_authenticated and current_user.role == "admin"


# -----------------------------
# AUDIT LOG HELPER
# -----------------------------

def add_audit_log(action, details=""):

    log = AuditLog(
        user_id=current_user.id,
        action=action,
        details=details
    )

    db.session.add(log)


# -----------------------------
# WHATSAPP PHONE HELPER
# -----------------------------

def format_whatsapp_phone(phone):

    phone = (phone or "").strip()

    # Keep digits only, while allowing Sri Lankan local/international formats.
    digits = "".join(character for character in phone if character.isdigit())

    if digits.startswith("0"):
        return "94" + digits[1:]

    if digits.startswith("94"):
        return digits

    return digits

    # =========================================
# SMS HELPER
# =========================================

def format_sms_phone(phone):

    phone = (phone or "").strip()

    digits = "".join(
        character
        for character in phone
        if character.isdigit()
    )

    if digits.startswith("0"):
        return "94" + digits[1:]

    if digits.startswith("94"):
        return digits

    return digits


def send_sms(phone, message):

    api_token = os.getenv("TEXTLK_API_TOKEN")
    sender_id = os.getenv(
        "TEXTLK_SENDER_ID",
        "TextLKDemo"
    )

    if not api_token:
        print("SMS skipped: TEXTLK_API_TOKEN is missing.")
        return False


    recipient = format_sms_phone(phone)


    payload = {
        "recipient": recipient,
        "sender_id": sender_id,
        "type": "plain",
        "message": message
    }


    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }


    try:

        response = requests.post(
            "https://app.text.lk/api/v3/sms/send",
            json=payload,
            headers=headers,
            timeout=10
        )

        if response.ok:

            print(
                f"SMS sent successfully to {recipient}"
            )

            return True


        print(
            "SMS failed:",
            response.status_code,
            response.text
        )

        return False


    except requests.RequestException as error:

        print(
            "SMS connection error:",
            error
        )

        return False

# =========================================
# HOME
# =========================================

@app.route("/")
def home():
    return render_template("index.html")


# =========================================
# LOGIN
# =========================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):

            if not user.is_active_user:
                flash("Your account is inactive.", "danger")
                return redirect(url_for("login"))

            login_user(user)
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


# =========================================
# DASHBOARD
# =========================================

@app.route("/dashboard")
@login_required
def dashboard():

    total_customers = Customer.query.count()
    total_visits = Visit.query.count()

    available_rewards = Reward.query.filter_by(
        status="available"
    ).count()

    return render_template(
        "dashboard.html",
        total_customers=total_customers,
        total_visits=total_visits,
        available_rewards=available_rewards
    )


# =========================================
# ADD CUSTOMER
# =========================================

@app.route("/customers/add", methods=["GET", "POST"])
@login_required
def add_customer():

    if request.method == "POST":

        full_name = request.form.get(
            "full_name",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip()

        gender = request.form.get(
            "gender",
            ""
        ).strip()


        # =====================================
        # REQUIRED FIELD VALIDATION
        # =====================================

        if not full_name or not phone or not gender:

            flash(
                "Name, phone number and customer category are required.",
                "danger"
            )

            return redirect(
                url_for("add_customer")
            )


        # =====================================
        # PHONE VALIDATION
        # =====================================

        phone_digits = (
            phone
            .replace(" ", "")
            .replace("-", "")
        )

        if not phone_digits.isdigit():

            flash(
                "Phone number must contain digits only.",
                "danger"
            )

            return redirect(
                url_for("add_customer")
            )


        if len(phone_digits) < 9 or len(phone_digits) > 15:

            flash(
                "Please enter a valid phone number.",
                "danger"
            )

            return redirect(
                url_for("add_customer")
            )


        phone = phone_digits


        # =====================================
        # EMAIL VALIDATION
        # =====================================

        if email:

            if (
                "@" not in email
                or "." not in email.split("@")[-1]
            ):

                flash(
                    "Please enter a valid email address.",
                    "danger"
                )

                return redirect(
                    url_for("add_customer")
                )


        # =====================================
        # DUPLICATE PHONE CHECK
        # =====================================

        existing_customer = Customer.query.filter_by(
            phone=phone
        ).first()

        if existing_customer:

            flash(
                "A customer with this phone number already exists.",
                "danger"
            )

            return redirect(
                url_for("add_customer")
            )


        # =====================================
        # GENERATE LOYALTY DETAILS
        # =====================================

        loyalty_number = (
            "HS-" +
            uuid.uuid4().hex[:8].upper()
        )

        qr_token = uuid.uuid4().hex


        # =====================================
        # CREATE CUSTOMER
        # =====================================

        customer = Customer(

            loyalty_number=loyalty_number,

            full_name=full_name,

            phone=phone,

            email=email if email else None,

            gender=gender,

            current_punches=0,

            qr_token=qr_token
        )


        db.session.add(customer)


        add_audit_log(
            "Customer Registered",
            (
                f"Customer: {customer.full_name}, "
                f"Loyalty: {customer.loyalty_number}"
            )
        )


        db.session.commit()


        flash(
            f"Customer registered successfully. Loyalty No: {loyalty_number}",
            "success"
        )


        return redirect(
            url_for(
                "customer_profile",
                customer_id=customer.id
            )
        )


    return render_template(
        "add_customer.html"
    )

# =========================================
# CUSTOMER LIST
# =========================================

@app.route("/customers")
@login_required
def customers():

    search = request.args.get("search", "").strip()

    query = Customer.query

    if search:
        query = query.filter(
            db.or_(
                Customer.full_name.ilike(f"%{search}%"),
                Customer.phone.ilike(f"%{search}%"),
                Customer.loyalty_number.ilike(f"%{search}%")
            )
        )

    customer_list = query.order_by(
        Customer.created_at.desc()
    ).all()

    return render_template(
        "customers.html",
        customers=customer_list,
        search=search
    )


# =========================================
# CUSTOMER PROFILE
# =========================================

@app.route("/customers/<int:customer_id>")
@login_required
def customer_profile(customer_id):

    customer = db.get_or_404(
        Customer,
        customer_id
    )

    visits = Visit.query.filter_by(
        customer_id=customer.id
    ).order_by(
        Visit.visit_date.desc()
    ).all()

    rewards = Reward.query.filter_by(
        customer_id=customer.id
    ).order_by(
        Reward.earned_at.desc()
    ).all()

    # Customer's public loyalty-card link.
    loyalty_url = url_for(
        "public_loyalty_card",
        qr_token=customer.qr_token,
        _external=True
    )

    # Normal WhatsApp destination used by the permanent
    # "WhatsApp Loyalty Card" button.
    whatsapp_phone = format_whatsapp_phone(
        customer.phone
    )

    # These values are supplied only immediately after
    # a successful visit has been recorded.
    visit_whatsapp_phone = request.args.get(
        "whatsapp_phone",
        ""
    )

    visit_whatsapp_message = request.args.get(
        "whatsapp_message",
        ""
    )

    return render_template(
        "customer_profile.html",
        customer=customer,
        visits=visits,
        rewards=rewards,
        loyalty_url=loyalty_url,
        whatsapp_phone=whatsapp_phone,
        visit_whatsapp_phone=visit_whatsapp_phone,
        visit_whatsapp_message=visit_whatsapp_message
    )


# =========================================
# RECORD VISIT
# =========================================

@app.route(
    "/customers/<int:customer_id>/visit",
    methods=["GET", "POST"]
)
@login_required
def record_visit(customer_id):

    customer = db.get_or_404(
        Customer,
        customer_id
    )

    if request.method == "POST":

        service_name = request.form.get(
            "service_name",
            ""
        ).strip()

        price_raw = request.form.get(
            "original_price",
            ""
        ).strip()


        # =====================================
        # REQUIRED FIELD VALIDATION
        # =====================================

        if not service_name or not price_raw:

            flash(
                "Service name and price are required.",
                "danger"
            )

            return redirect(
                url_for(
                    "record_visit",
                    customer_id=customer.id
                )
            )


        # =====================================
        # PRICE VALIDATION
        # =====================================

        try:
            original_price = float(price_raw)

        except ValueError:

            flash(
                "Please enter a valid price.",
                "danger"
            )

            return redirect(
                url_for(
                    "record_visit",
                    customer_id=customer.id
                )
            )


        if original_price <= 0:

            flash(
                "Price must be greater than zero.",
                "danger"
            )

            return redirect(
                url_for(
                    "record_visit",
                    customer_id=customer.id
                )
            )


        if original_price > 1000000:

            flash(
                "Service price is too large. Please check the amount.",
                "danger"
            )

            return redirect(
                url_for(
                    "record_visit",
                    customer_id=customer.id
                )
            )


        # =====================================
        # LOYALTY CYCLE VALIDATION
        # =====================================

        if customer.current_punches >= 10:

            flash(
                "This loyalty cycle already has 10 visits.",
                "danger"
            )

            return redirect(
                url_for(
                    "customer_profile",
                    customer_id=customer.id
                )
            )


        # =====================================
        # CALCULATE VISIT
        # =====================================

        next_punch = customer.current_punches + 1

        discount_percent = 0

        final_price = original_price


        # Visit 5 = 25% discount.
        if next_punch == 5:

            discount_percent = 25

            final_price = original_price * 0.75


        # =====================================
        # CREATE VISIT
        # =====================================

        visit = Visit(
            customer_id=customer.id,
            staff_id=current_user.id,
            service_name=service_name,
            original_price=original_price,
            discount_percent=discount_percent,
            final_price=final_price,
            punch_number=next_punch
        )

        db.session.add(visit)

        customer.current_punches = next_punch


        # =====================================
        # VISIT 10 REWARD
        # =====================================

        if next_punch == 10:

            reward = Reward(
                customer_id=customer.id,
                reward_type="Free Facial",
                status="available"
            )

            db.session.add(reward)


        # =====================================
        # AUDIT LOG
        # =====================================

        add_audit_log(
            "Visit Recorded",
            (
                f"Customer: {customer.full_name}, "
                f"Visit: {next_punch}, "
                f"Service: {service_name}, "
                f"Final Price: LKR {final_price:.2f}"
            )
        )


        db.session.commit()


        # =====================================
        # FLASH MESSAGE
        # =====================================

        if next_punch == 5:

            flash(
                "Visit recorded successfully. 25% discount applied.",
                "success"
            )

        elif next_punch == 10:

            flash(
                "10th visit completed! Free Facial reward is now available.",
                "success"
            )

        else:

            flash(
                f"Visit {next_punch} recorded successfully.",
                "success"
            )


        # =====================================
        # THANK-YOU WHATSAPP MESSAGE
        # =====================================

        loyalty_url = url_for(
            "public_loyalty_card",
            qr_token=customer.qr_token,
            _external=True
        )

        whatsapp_phone = format_whatsapp_phone(
            customer.phone
        )


        if next_punch == 5:

            whatsapp_message = (
                f"Thank you for visiting HS Singapore Salon, "
                f"{customer.full_name}!\n\n"
                f"Visit {next_punch} of 10 has been recorded successfully.\n\n"
                f"Your 25% loyalty discount has been applied.\n\n"
                f"Next reward:\n"
                f"Visit 10 - FREE FACIAL\n\n"
                f"View your digital loyalty card:\n"
                f"{loyalty_url}\n\n"
                f"Thank you for choosing HS Singapore Salon."
            )


        elif next_punch == 10:

            whatsapp_message = (
                f"Congratulations, {customer.full_name}!\n\n"
                f"You have completed Visit 10 at HS Singapore Salon.\n\n"
                f"Your FREE FACIAL reward is now available.\n\n"
                f"View your digital loyalty card:\n"
                f"{loyalty_url}\n\n"
                f"Thank you for being a valued loyalty member."
            )


        else:

            if next_punch < 5:
                next_reward = "Visit 5 - 25% OFF"
            else:
                next_reward = "Visit 10 - FREE FACIAL"

            whatsapp_message = (
                f"Thank you for visiting HS Singapore Salon, "
                f"{customer.full_name}!\n\n"
                f"Your loyalty visit has been recorded successfully.\n\n"
                f"Progress: {next_punch} / 10 Visits\n\n"
                f"Next reward:\n"
                f"{next_reward}\n\n"
                f"View your digital loyalty card:\n"
                f"{loyalty_url}\n\n"
                f"We look forward to seeing you again!"
            )


        # PRG pattern: redirect after POST so refreshing the profile
        # cannot submit the same visit again.
        return redirect(
            url_for(
                "customer_profile",
                customer_id=customer.id,
                whatsapp_phone=whatsapp_phone,
                whatsapp_message=whatsapp_message
            )
        )


    return render_template(
        "record_visit.html",
        customer=customer
    )


@app.route("/rewards")
@login_required
def rewards():

    reward_list = Reward.query.order_by(
        Reward.earned_at.desc()
    ).all()

    return render_template(
        "rewards.html",
        rewards=reward_list
    )
@app.route("/rewards/<int:reward_id>/redeem", methods=["POST"])
@login_required
def redeem_reward(reward_id):

    reward = db.get_or_404(
        Reward,
        reward_id
    )

    if reward.status == "redeemed":

        flash(
            "This reward has already been redeemed.",
            "danger"
        )

        return redirect(
            url_for("rewards")
        )

    from datetime import datetime

    reward.status = "redeemed"
    reward.redeemed_at = datetime.utcnow()

    add_audit_log(
    "Reward Redeemed",
    (
        f"Customer ID: {reward.customer_id}, "
        f"Reward: {reward.reward_type}"
    )
  )

    db.session.commit()

    flash(
        "Free Facial reward redeemed successfully.",
        "success"
    )

    return redirect(
        url_for(
            "customer_profile",
            customer_id=reward.customer_id
        )
    )
@app.route(
    "/customers/<int:customer_id>/new-cycle",
    methods=["POST"]
)
@login_required
def start_new_cycle(customer_id):

    customer = db.get_or_404(
        Customer,
        customer_id
    )

    # Customer must complete all 10 visits first
    if customer.current_punches < 10:

        flash(
            "This customer has not completed the current loyalty cycle yet.",
            "danger"
        )

        return redirect(
            url_for(
                "customer_profile",
                customer_id=customer.id
            )
        )

    # Check whether a Free Facial reward is still available
    available_reward = Reward.query.filter_by(
        customer_id=customer.id,
        reward_type="Free Facial",
        status="available"
    ).first()

    if available_reward:

        flash(
            "Redeem the available Free Facial reward before starting a new loyalty cycle.",
            "danger"
        )

        return redirect(
            url_for(
                "customer_profile",
                customer_id=customer.id
            )
        )

    # Start new cycle
    customer.current_punches = 0

    db.session.commit()

    flash(
        "New loyalty cycle started successfully.",
        "success"
    )

    return redirect(
        url_for(
            "customer_profile",
            customer_id=customer.id
        )
    )

@app.route("/record-visit")
@login_required
def record_visit_search():

    search = request.args.get("search", "").strip()

    customers_found = []

    if search:
        customers_found = Customer.query.filter(
            db.or_(
                Customer.full_name.ilike(f"%{search}%"),
                Customer.phone.ilike(f"%{search}%"),
                Customer.loyalty_number.ilike(f"%{search}%")
            )
        ).order_by(
            Customer.full_name.asc()
        ).all()

    return render_template(
        "record_visit_search.html",
        customers=customers_found,
        search=search
    )

@app.route("/customers/<int:customer_id>/qr")
@login_required
def customer_qr(customer_id):

    customer = db.get_or_404(
        Customer,
        customer_id
    )

    qr_data = url_for(
    "public_loyalty_card",
    qr_token=customer.qr_token,
    _external=True
    )

    qr = qrcode.QRCode(
        version=1,
        box_size=8,
        border=3
    )

    qr.add_data(qr_data)
    qr.make(fit=True)

    image = qr.make_image(
        fill_color="black",
        back_color="white"
    )

    image_buffer = io.BytesIO()

    image.save(
        image_buffer,
        format="PNG"
    )

    image_buffer.seek(0)

    return send_file(
        image_buffer,
        mimetype="image/png"
    )
@app.route("/loyalty/<qr_token>")
def public_loyalty_card(qr_token):

    customer = Customer.query.filter_by(
        qr_token=qr_token
    ).first_or_404()

    rewards = Reward.query.filter_by(
        customer_id=customer.id
    ).order_by(
        Reward.earned_at.desc()
    ).all()

    return render_template(
        "public_loyalty_card.html",
        customer=customer,
        rewards=rewards
    )
@app.route("/staff")
@login_required
def staff_management():

    if not admin_required():
        flash(
            "You do not have permission to access Staff Management.",
            "danger"
        )
        return redirect(url_for("dashboard"))

    staff_list = User.query.order_by(
        User.created_at.desc()
    ).all()

    return render_template(
        "staff.html",
        staff_list=staff_list
    )
@app.route("/staff/add", methods=["GET", "POST"])
@login_required
def add_staff():

    if not admin_required():
        flash(
            "Only administrators can create staff accounts.",
            "danger"
        )
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        full_name = request.form.get(
            "full_name",
            ""
        ).strip()

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        role = request.form.get(
            "role",
            "staff"
        ).strip()

        if not full_name or not username or not password:
            flash(
                "Full name, username and password are required.",
                "danger"
            )
            return redirect(url_for("add_staff"))

        if role not in ["staff", "admin"]:
            role = "staff"

        existing_user = User.query.filter_by(
            username=username
        ).first()

        if existing_user:
            flash(
                "This username already exists.",
                "danger"
            )
            return redirect(url_for("add_staff"))

        if len(password) < 8:
            flash(
                "Password must contain at least 8 characters.",
                "danger"
            )
            return redirect(url_for("add_staff"))

        new_user = User(
            full_name=full_name,
            username=username,
            password_hash=generate_password_hash(password),
            role=role,
            is_active_user=True
        )

        db.session.add(new_user)

        add_audit_log(
           "Staff Created",
           (
             f"Staff: {new_user.full_name}, "
             f"Username: {new_user.username}, "
             f"Role: {new_user.role}"
           )
        )

        db.session.commit()

        flash(
            "Staff account created successfully.",
            "success"
        )

        return redirect(
            url_for("staff_management")
        )

    return render_template("add_staff.html")

@app.route(
    "/staff/<int:user_id>/toggle",
    methods=["POST"]
)
@login_required
def toggle_staff(user_id):

    if not admin_required():
        flash(
            "Only administrators can update staff accounts.",
            "danger"
        )
        return redirect(url_for("dashboard"))

    user = db.get_or_404(
        User,
        user_id
    )

    if user.id == current_user.id:
        flash(
            "You cannot deactivate your own account.",
            "danger"
        )
        return redirect(
            url_for("staff_management")
        )

    user.is_active_user = not user.is_active_user

    if user.is_active_user:

       add_audit_log(
          "Staff Activated",
        (
            f"Staff: {user.full_name}, "
            f"Username: {user.username}"
        )
    )

    else:

        add_audit_log(
           "Staff Deactivated",
        (
            f"Staff: {user.full_name}, "
            f"Username: {user.username}"
        )
       )

    db.session.commit()

    if user.is_active_user:
        flash(
            f"{user.full_name} has been activated.",
            "success"
        )
    else:
        flash(
            f"{user.full_name} has been deactivated.",
            "success"
        )

    return redirect(
        url_for("staff_management")
    )

@app.route("/scan")
@login_required
def scan_customer():
    return render_template("scan_customer.html")

@app.route("/scan/lookup")
@login_required
def scan_lookup():

    qr_value = request.args.get("value", "").strip()

    if not qr_value:
        flash("Invalid QR code.", "danger")
        return redirect(url_for("scan_customer"))

    # Extract token if the QR contains the public loyalty URL
    token = qr_value.rstrip("/").split("/")[-1]

    customer = Customer.query.filter_by(
        qr_token=token
    ).first()

    if not customer:
        flash(
            "Customer loyalty QR code was not recognized.",
            "danger"
        )
        return redirect(url_for("scan_customer"))

    return redirect(
        url_for(
            "customer_profile",
            customer_id=customer.id
        )
    )

@app.route("/audit-logs")
@login_required
def audit_logs():

    if not admin_required():
        flash(
            "You do not have permission to view audit logs.",
            "danger"
        )
        return redirect(url_for("dashboard"))

    search = request.args.get("search", "").strip()
    action_filter = request.args.get("action", "").strip()

    query = AuditLog.query.join(User)

    if search:
        query = query.filter(
            db.or_(
                User.full_name.ilike(f"%{search}%"),
                User.username.ilike(f"%{search}%"),
                AuditLog.details.ilike(f"%{search}%")
            )
        )

    if action_filter:
        query = query.filter(
            AuditLog.action == action_filter
        )

    logs = query.order_by(
        AuditLog.created_at.desc()
    ).all()

    actions = [
        row[0]
        for row in db.session.query(
            AuditLog.action
        ).distinct().order_by(
            AuditLog.action.asc()
        ).all()
    ]

    return render_template(
        "audit_logs.html",
        logs=logs,
        search=search,
        action_filter=action_filter,
        actions=actions
    )

# =========================================
# LOGOUT
# =========================================

@app.route("/logout")
@login_required
def logout():

    logout_user()
    return redirect(url_for("login"))

@app.errorhandler(404)
def page_not_found(error):
    return render_template(
        "404.html"
    ), 404

@app.errorhandler(500)
def internal_server_error(error):

    db.session.rollback()

    return render_template(
        "500.html"
    ), 500

@app.route("/test-sms")
@login_required
def test_sms():

    message = (
        "HS Singapore Salon: "
        "This is a test loyalty system SMS."
    )

    success = send_sms(
        "0724008359",
        message
    )

    if success:
        return "SMS sent successfully."

    return "SMS failed. Check terminal/API settings."

# =========================================
# RUN APPLICATION
# =========================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )