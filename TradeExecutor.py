import datetime
import logging
import pandas as pd
from SLManagement import SLManagement
from OptionDataManagement import OptionDataManagement
from TradeManager import TradeManager
from WebSocketManager import WebSocketManager
from config import TRADE_SIZE, INDEX_DETAILS, current_index
import logging
from time import sleep
from datetime import datetime, time


import pytz
from pydub import AudioSegment  # Correct import for AudioSegment
from pydub.playback import play  # Correct import for play
import simpleaudio as sa
import threading
import pygame


logger = logging.getLogger(__name__)


def play_bought_siren():
    try:
        # Initialize pygame mixer
        pygame.mixer.init()
        # Load the siren sound
        pygame.mixer.music.load("AlertSounds/alertSirenRingIPL.wav")
        # Play the siren sound
        pygame.mixer.music.play()
        # Wait until the sound finishes playing
        while pygame.mixer.music.get_busy():
            time.sleep(1)
    except Exception as e:
        logger.error(f"Error playing siren: {e}")
    finally:
        pygame.mixer.quit()


def play_bought_siren_threaded():
    return None
    # try:
    #     # thread = threading.Thread(target=play_bought_siren)
    #     # thread.start()
    # except Exception as e:
    #     logger.error(f"Error playing play_bought_siren_threaded: {e}")

def play_help_siren():
    try:
        # Initialize pygame mixer
        pygame.mixer.init()
        # Load the siren sound
        pygame.mixer.music.load("AlertSounds/alertSound1.wav")
        # Play the siren sound
        pygame.mixer.music.play()
        # Wait until the sound finishes playing
        while pygame.mixer.music.get_busy():
            time.sleep(1)
    except Exception as e:
        logger.error(f"Error playing siren: {e}")
    finally:
        pygame.mixer.quit()

def play_help_siren_threaded():
    return None
    # try:
    #     # thread = threading.Thread(target=play_help_siren)
    #     # thread.start()
    # except Exception as e:
    #     logger.error(f"Error playing play_help_siren_threaded: {e}")

class TradeExecutor:
    def __init__(self,config, trade_manager,webSocketManager, kite,index_data_management, twilio_client ):
        self.config = config
        self.webSocketManager=webSocketManager
        self.twilio_client = twilio_client
        self.webSocketManager.add_ltp_callback(self.sell_trade_on_ltp_update)
        self.trade_manager = trade_manager
        self.kite = kite
        self.processing = False
        self.index_data_management = index_data_management
        self.trades = pd.DataFrame(columns=["Date", "Type", "Entry Price", "Exit Price", "Profit/Loss"])
        logging.basicConfig(level=logging.INFO, filename='trade_execution.log', format='%(asctime)s - %(levelname)s - %(message)s')
        self.failureTerminatedOrderStatus = ["REJECTED", "CANCELLED"]
        self.successTerminatedOrderStatus = ["COMPLETED"]

    def send_whatsapp_message(self, message_text):
        try:
            # Send the WhatsApp message
            message = self.twilio_client.messages.create(
                body=message_text,
                from_=f'whatsapp:+14155238886',
                to=f'whatsapp:+917982171144'
            )
            return message.sid
        except Exception as e:
            logger.error(f"Error sending whatsapp message: {e}")
    def play_bought_siren(self):
        try:
            # Load the siren sound
            wave_obj = sa.WaveObject.from_wave_file("AlertSounds/alertSirenRingIPL.wav")
            play_obj = wave_obj.play()
            # play_obj.wait_done()  # Wait until sound has finished playing
        except Exception as e:
            logger.error(f"Error playing siren: {e}")


    def play_help_siren(self):
        try:
            # Load the siren sound
            wave_obj = sa.WaveObject.from_wave_file("AlertSounds/alertSound1.wav")
            play_obj = wave_obj.play()
            # play_obj.wait_done()  # Wait until sound has finished playing
        except Exception as e:
            logger.error(f"Error playing siren: {e}")


    def update_stoploss_target(self,last_option_data, index_details):
        index_instrument_token = index_details['instrument_token']
        logger.info(f"Time to Start updation process of stoploss & target for index instrument token : {index_instrument_token}")
        logger.info(f"Option Data Latest Row : {last_option_data}")
        try:
            logger.info(f"Finding active trade for index instrument token: {index_instrument_token}")
            active_trade = self.trade_manager.get_active_trade(index_instrument_token)
            if active_trade is None:
                logger.info(f"No Active trade found for Index Instrument Token: {index_instrument_token}")
                return
            logger.info(f"Active trade found for index instrument token: {index_instrument_token}")
            logger.info(f"Active trade Information : {active_trade}")
            stoploss_price = last_option_data['stoploss']
            target_price = active_trade['target_price']
            prev_stoploss_price = active_trade['stoploss_price']
            sl_order_id = active_trade['sl_order_id']
            if sl_order_id is None:
                logger.info(f"SL order was not present previously. So placing fresh SL order for tradingsymbol {active_trade['signal']['instrument']['tradingsymbol']} , quantity : {active_trade['quantity']} , stoploss_price : {stoploss_price}")
                sl_order_id = self.place_sl_order(active_trade['signal']['instrument']['tradingsymbol'], active_trade['quantity'], stoploss_price)
                if sl_order_id:
                    logger.info(f"Placed stoploss order for {sl_order_id}")
                    self.trade_manager.update_sl_order(index_instrument_token,
                                                       sl_order_id)
                    self.trade_manager.update_active_trade(index_instrument_token, stoploss_price, target_price)
                else:
                    logger.info(f"Not been able to place stoploss order. So retrying 5 times")
                    for _ in range(5):
                        logger.info(f"Attempt {_} : Placing stoploss order tradingsymbol : {active_trade['signal']['instrument']['tradingsymbol']} quantity : {active_trade['quantity']} stoploss_price : {stoploss_price}")
                        sl_order_id = self.place_sl_order(active_trade['signal']['instrument']['tradingsymbol'], active_trade['quantity'],
                                                          stoploss_price)
                        if sl_order_id:
                            logger.info(f"Attempt {_} : Placed stoploss order {sl_order_id}")
                            self.trade_manager.update_sl_order(index_instrument_token,sl_order_id)
                            self.trade_manager.update_active_trade(index_instrument_token, stoploss_price, target_price)
                            break
                        else:
                            logger.info(f"Attempt {_} : Not able to place stoploss order")
                    else:
                        logger.info(f"5 Attempts exhausted : Not able to place stoploss order, so getting active trade information to place sell order at market price")
                        active_trade = self.trade_manager.get_active_trade(index_instrument_token)
                        if active_trade:
                            logging.info(f"Active trade found. Placing sell order on market price for tradingsymbol : {active_trade['signal']['instrument']['tradingsymbol']} quantity : {active_trade['quantity']}")
                            for _ in range(5):
                                logger.info(f"Attempt {_} : Placing sell order tradingsymbol : {active_trade['signal']['instrument']['tradingsymbol']} quantity : {active_trade['quantity']}")
                                sell_order_id = self.place_order(
                                    variety="regular",
                                    tradingsymbol=active_trade['signal']['instrument']['tradingsymbol'],
                                    exchange="NFO",
                                    transaction_type="SELL",
                                    order_type="MARKET",
                                    quantity=active_trade['quantity'],
                                    product="MIS",
                                    validity="DAY"
                                )
                                if sell_order_id:
                                    logger.info(f"Attempt {_} : Sell order placed with order id {sell_order_id}")
                                    while True:
                                        logger.info(f"Attempt {_} : Checking the status of sell order id {sell_order_id}")
                                        orderHistory = self.check_order(sell_order_id)
                                        logger.info(f"Attempt {_} : Checked the status of sell order id {sell_order_id} with status as {orderHistory['status']}")
                                        status = orderHistory['status']
                                        if status == "COMPLETE":
                                            logger.info(f"Attempt {_} : Checked the status of completed sell order id {sell_order_id} with status as {orderHistory['status']}")
                                            average_exit_price = orderHistory['average_price']
                                            logger.info(f"Exited at market price as sl limit order failed")
                                            result = "Stopped out"
                                            ist = pytz.timezone('Asia/Kolkata')
                                            exit_datetime_obj = datetime.strptime(
                                                orderHistory['exchange_update_timestamp'], "%Y-%m-%d %H:%M:%S")
                                            exit_datetime_obj_ist = ist.localize(exit_datetime_obj)
                                            exit_date = exit_datetime_obj_ist
                                            average_entry_price = active_trade['average_entry_price']
                                            quantity = active_trade['quantity']
                                            profit_loss = (average_exit_price - average_entry_price) * quantity
                                            self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                                                   trade_time=exit_date,
                                                                                   profit_loss=profit_loss,
                                                                                   instrument_token=
                                                                                   self.index_data_management.index[
                                                                                       'instrument_token'],
                                                                                   average_exit_price=average_exit_price)
                                            self.record_trade(active_trade['signal'], active_trade['entry_price'], None,
                                                              profit_loss, quantity, result,
                                                              active_trade['stoploss_price'], exit_date,
                                                              average_entry_price, average_exit_price)
                                            logger.info(
                                                f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                                            self.webSocketManager.unsubscribe([active_trade['signal']['instrument_token']])
                                            try:
                                                self.send_whatsapp_message(f"Trade Exited...\nBuying Algo,\nResult: {result},\nStrike: {active_trade['signal']['symbol']},\nIndex: {index_details['tradingsymbol']},\nEntry Time: {active_trade['actual_entry_date']},\nExit Time: {exit_date},\nEntry Price: {active_trade['entry_price']},\nActual Entry Price: {active_trade['average_entry_price']},\nActual Exit Price: {average_exit_price},\nP&L = {profit_loss}")
                                            except Exception as whatsappException:
                                                self.send_whatsapp_message(f"Buying Algo,\nA Trade was Completed but Whatsapp Message failed due to argument error.")


                                            break
                                        elif status in self.failureTerminatedOrderStatus:
                                            logger.info(f"Attempt {_} : Checked the status of failed sell order id {sell_order_id} with status as {orderHistory['status']}")
                                            logger.info(f"Attempt {_} : Sell Order also failed after SL order failure, so calling, emailing Dagar and raising alarm siren")
                                            # play_help_siren_threaded()
                                            average_exit_price = last_option_data['close']
                                            result = "Stopped out"
                                            exit_date = last_option_data['date']
                                            average_entry_price = active_trade['average_entry_price']
                                            quantity = active_trade['quantity']
                                            exit_price = active_trade['stoploss_price']
                                            profit_loss = (average_exit_price - average_entry_price) * quantity
                                            self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                                                   trade_time=exit_date,
                                                                                   profit_loss=profit_loss,
                                                                                   instrument_token=
                                                                                   self.index_data_management.index[
                                                                                       'instrument_token'],
                                                                                   average_exit_price=average_exit_price)
                                            self.record_trade(active_trade['signal'], active_trade['entry_price'],
                                                              exit_price,
                                                              profit_loss, quantity, result,
                                                              active_trade['stoploss_price'], exit_date,
                                                              average_entry_price, average_exit_price)
                                            logger.info(
                                                f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                                            self.webSocketManager.unsubscribe(
                                                [active_trade['signal']['instrument_token']])
                                            try:
                                                self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure,\nIndex: {index_details['tradingsymbol']},\nStrike: {active_trade['signal']['symbol']}")
                                            except Exception as whatsappException:
                                                self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure. Whatsapp Message also failed due to argument error.")

                                            break
                                        else:
                                            logger.info(f"Attempt {_} : Checked the status of sell order id {sell_order_id} with status as {orderHistory['status']}")
                                    logger.info(f"Reached to selling last step when SL failed.")
                                    break
                                else:
                                    logger.info(f"Attempt {_} : Not been able to place sell order. so retrying")
                            else:
                                logger.info(f"Attempts exhausted : Not able to place sell order, so calling, emailing, whatsapp Dagar and raising alarm siren")
                                average_exit_price = last_option_data['close']
                                result = "Stopped out"
                                exit_date = last_option_data['date']
                                average_entry_price = active_trade['average_entry_price']
                                quantity = active_trade['quantity']
                                exit_price = active_trade['stoploss_price']
                                profit_loss = (average_exit_price - average_entry_price) * quantity
                                self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                                       trade_time=exit_date,
                                                                       profit_loss=profit_loss,
                                                                       instrument_token=
                                                                       self.index_data_management.index[
                                                                           'instrument_token'],
                                                                       average_exit_price=average_exit_price)
                                self.record_trade(active_trade['signal'], active_trade['entry_price'], exit_price,
                                                  profit_loss, quantity, result,
                                                  active_trade['stoploss_price'], exit_date,
                                                  average_entry_price, average_exit_price)
                                logger.info(
                                    f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                                self.webSocketManager.unsubscribe([active_trade['signal']['instrument_token']])
                                try:
                                    self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure,\nIndex: {index_details['tradingsymbol']},\nStrike: {active_trade['signal']['symbol']}")
                                except Exception as whatsappException:
                                    self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure. Whatsapp Message also failed due to argument error.")
                                # play_help_siren_threaded()
                        else:
                            logger.info(f"No Active Trade found. It may have been exited manually by Dagar")
            else:
                logger.info(f"Checking the status of stoploss order id {sl_order_id}")
                orderHistory = self.check_order(sl_order_id)
                logger.info(f"Checked the status of stoploss order id {sl_order_id} with status as {orderHistory['status']}")
                status = orderHistory['status']
                if status == "COMPLETE":
                    logger.info(f"Checked the status of completed stoploss order id {sl_order_id} with status as {orderHistory['status']}")
                    average_exit_price = orderHistory['average_price']
                    result = "Stopped out"
                    ist = pytz.timezone('Asia/Kolkata')
                    exit_datetime_obj = datetime.strptime(
                        orderHistory['exchange_update_timestamp'], "%Y-%m-%d %H:%M:%S")
                    exit_datetime_obj_ist = ist.localize(exit_datetime_obj)
                    exit_date = exit_datetime_obj_ist
                    average_entry_price = active_trade['average_entry_price']
                    quantity = active_trade['quantity']
                    exit_price = active_trade['stoploss_price']
                    profit_loss = (average_exit_price - average_entry_price) * quantity
                    self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                           trade_time=exit_date,
                                                           profit_loss=profit_loss,
                                                           instrument_token=
                                                           self.index_data_management.index[
                                                               'instrument_token'],
                                                           average_exit_price=average_exit_price)
                    self.record_trade(active_trade['signal'], active_trade['entry_price'], exit_price,
                                      profit_loss, quantity, result,
                                      active_trade['stoploss_price'], exit_date,
                                      average_entry_price, average_exit_price)
                    logger.info(
                        f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                    self.webSocketManager.unsubscribe([active_trade['signal']['instrument_token']])
                    try:
                        self.send_whatsapp_message(f"Trade Exited...\nBuying Algo,\nResult: {result},\nStrike: {active_trade['signal']['symbol']},\nIndex: {index_details['tradingsymbol']},\nEntry Time: {active_trade['actual_entry_date']},\nExit Time: {exit_date},\nEntry Price: {active_trade['entry_price']},\nActual Entry Price: {active_trade['average_entry_price']},\nActual Exit Price: {average_exit_price},\nP&L = {profit_loss}")
                    except Exception as whatsappException:
                        self.send_whatsapp_message(f"Buying Algo,\nA Trade was Completed but Whatsapp Message failed due to argument error.")
                elif status in self.failureTerminatedOrderStatus:
                    logger.info(f"A SL modification failed as SL was cancelled previously. Manually Verify once that this Trade has been exited.,\nStrike: {active_trade['signal']['symbol']},\nIndex: {index_details['tradingsymbol']}")
                    average_exit_price = last_option_data['close']
                    result = "Stopped out"
                    exit_date = last_option_data['date']
                    average_entry_price = active_trade['average_entry_price']
                    quantity = active_trade['quantity']
                    exit_price = active_trade['stoploss_price']
                    profit_loss = (average_exit_price - average_entry_price) * quantity
                    self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                           trade_time=exit_date,
                                                           profit_loss=profit_loss,
                                                           instrument_token=
                                                           self.index_data_management.index[
                                                               'instrument_token'],
                                                           average_exit_price=average_exit_price)
                    self.record_trade(active_trade['signal'], active_trade['entry_price'], exit_price,
                                      profit_loss, quantity, result,
                                      active_trade['stoploss_price'], exit_date,
                                      average_entry_price, average_exit_price)
                    logger.info(
                        f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                    self.webSocketManager.unsubscribe([active_trade['signal']['instrument_token']])
                    try:
                        self.send_whatsapp_message(f"A SL modification failed as SL was cancelled previously. Manually Verify once that this Trade has been exited.,\nStrike: {active_trade['signal']['symbol']},\nIndex: {index_details['tradingsymbol']}")
                    except Exception as whatsappException:
                        self.send_whatsapp_message(f"Buying Algo,\nA SL modification failed as SL was cancelled previously. Manually Verify once that this Trade has been exited. but Whatsapp Message failed due to argument error.")
                else:
                    logger.info(f"SL order was present previously. Now modifying this SL order with updated Stoploss")
                    if stoploss_price > prev_stoploss_price:
                        logger.info(f"Current stoploss price is greater than existing stoploss price so modifying SL order")
                        for _ in range(5):
                            if self.modify_order(sl_order_id, "regular",price=(stoploss_price* 0.98),trigger_price=stoploss_price) is not None:
                                logger.info(f"Attempt {_} : Modified SL Limit Order successfully at Stoploss Trigger Price: {stoploss_price}")
                                self.trade_manager.update_active_trade(index_instrument_token, stoploss_price, target_price)
                                break
                            else:
                                logger.info(f"Attempt {_} : Modification of SL Limit Order failed at Stoploss Trigger Price: {stoploss_price}")
                        else:
                            logger.info(f"SL Limit Modify order failed 5 times. Now Time to cancel this SL limit order and place a fresh Market Sell Order")
                            cancelled_sl_order_id = self.cancel_order(sl_order_id)
                            if cancelled_sl_order_id is  None:
                                logger.info(f"Could not cancel sl order")
                                logger.info(f"Cancel Order failed, so calling, emailing Dagar and raising alarm siren")
                                average_exit_price = last_option_data['close']
                                result = "Stopped out"
                                exit_date = last_option_data['date']
                                average_entry_price = active_trade['average_entry_price']
                                quantity = active_trade['quantity']
                                exit_price = active_trade['stoploss_price']
                                profit_loss = (average_exit_price - average_entry_price) * quantity
                                self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                                       trade_time=exit_date,
                                                                       profit_loss=profit_loss,
                                                                       instrument_token=
                                                                       self.index_data_management.index[
                                                                           'instrument_token'],
                                                                       average_exit_price=average_exit_price)
                                self.record_trade(active_trade['signal'], active_trade['entry_price'], exit_price,
                                                  profit_loss, quantity, result,
                                                  active_trade['stoploss_price'], exit_date,
                                                  average_entry_price, average_exit_price)
                                logger.info(
                                    f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                                self.webSocketManager.unsubscribe([active_trade['signal']['instrument_token']])
                                try:
                                    self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSL modify failed and SL cancel also failed. Exit the trade manually.\nIndex: {index_details['tradingsymbol']},\nStrike: {active_trade['signal']['symbol']}")
                                except Exception as whatsappException:
                                    self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSL modify failed and SL cancel also failed. Exit the trade manually. Whatsapp Message also failed due to argument error.")
                                # play_help_siren_threaded()
                            else:
                                logger.info(f"Cancelled sl order. Now placing sell market order")
                                for _ in range(5):
                                    logger.info(f"Attempt {_} : Placing sell order tradingsymbol : {active_trade['signal']['instrument']['tradingsymbol']} quantity : {active_trade['quantity']}")
                                    sell_order_id = self.place_order(
                                        variety="regular",
                                        tradingsymbol=active_trade['signal']['instrument']['tradingsymbol'],
                                        exchange="NFO",
                                        transaction_type="SELL",
                                        order_type="MARKET",
                                        quantity=active_trade['quantity'],
                                        product="MIS",
                                        validity="DAY"
                                    )
                                    if sell_order_id:
                                        logger.info(f"Attempt {_} : Sell order placed with order id {sell_order_id}")
                                        while True:
                                            logger.info(f"Attempt {_} : Checking the status of sell order id {sell_order_id}")
                                            orderHistory = self.check_order(sell_order_id)
                                            logger.info(f"Attempt {_} : Checked the status of sell order id {sell_order_id} with status as {orderHistory['status']}")
                                            status = orderHistory['status']
                                            if status == "COMPLETE":
                                                logger.info(f"Attempt {_} : Checked the status of completed sell order id {sell_order_id} with status as {orderHistory['status']}")
                                                average_exit_price = orderHistory['average_price']
                                                logger.info(f"Exited at market price as sl limit order modification failed")
                                                result = "Stopped out"
                                                ist = pytz.timezone('Asia/Kolkata')
                                                exit_datetime_obj = datetime.strptime(
                                                    orderHistory['exchange_update_timestamp'], "%Y-%m-%d %H:%M:%S")
                                                exit_datetime_obj_ist = ist.localize(exit_datetime_obj)
                                                exit_date = exit_datetime_obj_ist
                                                average_entry_price = active_trade['average_entry_price']
                                                quantity = active_trade['quantity']
                                                profit_loss = (average_exit_price - average_entry_price) * quantity
                                                self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                                                       trade_time=exit_date,
                                                                                       profit_loss=profit_loss,
                                                                                       instrument_token=
                                                                                       self.index_data_management.index[
                                                                                           'instrument_token'],
                                                                                       average_exit_price=average_exit_price)
                                                self.record_trade(active_trade['signal'], active_trade['entry_price'], None,
                                                                  profit_loss, quantity, result,
                                                                  active_trade['stoploss_price'], exit_date,
                                                                  average_entry_price, average_exit_price)
                                                logger.info(f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                                                self.webSocketManager.unsubscribe([active_trade['signal']['instrument_token']])
                                                try:
                                                    self.send_whatsapp_message(f"Trade Exited...\nBuying Algo,\nResult: {result},\nStrike: {active_trade['signal']['symbol']},\nIndex: {index_details['tradingsymbol']},\nEntry Time: {active_trade['actual_entry_date']},\nExit Time: {exit_date},\nEntry Price: {active_trade['entry_price']},\nActual Entry Price: {active_trade['average_entry_price']},\nActual Exit Price: {average_exit_price},\nP&L = {profit_loss}")
                                                except Exception as whatsappException:
                                                    self.send_whatsapp_message(f"Buying Algo,\nA Trade was Completed but Whatsapp Message failed due to argument error.")
                                                break
                                            elif status in self.failureTerminatedOrderStatus:
                                                logger.info(f"Attempt {_} : Checked the status of failed sell order id {sell_order_id} with status as {orderHistory['status']}")
                                                logger.info(f"Attempt {_} : Sell Order also failed after SL order failure, so calling, emailing Dagar and raising alarm siren")
                                                average_exit_price = last_option_data['close']
                                                result = "Stopped out"
                                                exit_date = last_option_data['date']
                                                average_entry_price = active_trade['average_entry_price']
                                                quantity = active_trade['quantity']
                                                exit_price = active_trade['stoploss_price']
                                                profit_loss = (average_exit_price - average_entry_price) * quantity
                                                self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                                                       trade_time=exit_date,
                                                                                       profit_loss=profit_loss,
                                                                                       instrument_token=
                                                                                       self.index_data_management.index[
                                                                                           'instrument_token'],
                                                                                       average_exit_price=average_exit_price)
                                                self.record_trade(active_trade['signal'], active_trade['entry_price'],
                                                                  exit_price,
                                                                  profit_loss, quantity, result,
                                                                  active_trade['stoploss_price'], exit_date,
                                                                  average_entry_price, average_exit_price)
                                                logger.info(
                                                    f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                                                self.webSocketManager.unsubscribe(
                                                    [active_trade['signal']['instrument_token']])
                                                try:
                                                    self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure,\nIndex: {index_details['tradingsymbol']},\nStrike: {active_trade['signal']['symbol']}")
                                                except Exception as whatsappException:
                                                    self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure. Whatsapp Message also failed due to argument error.")

                                                # play_help_siren_threaded()
                                                break
                                            else:
                                                logger.info(f"Attempt {_} : Checked the status of sell order id {sell_order_id} with status as {orderHistory['status']}")
                                        logger.info(f"Reached to selling last step when SL modification failed.")
                                        break
                                    else:
                                        logger.info(f"Attempt {_} : Not been able to place sell order. so retrying")
                                else:
                                    logger.info(f"Attempts exhausted : Not able to place sell order, so calling, emailing, whatsapp Dagar and raising alarm siren")
                                    average_exit_price = last_option_data['close']
                                    result = "Stopped out"
                                    exit_date = last_option_data['date']
                                    average_entry_price = active_trade['average_entry_price']
                                    quantity = active_trade['quantity']
                                    exit_price = active_trade['stoploss_price']
                                    profit_loss = (average_exit_price - average_entry_price) * quantity
                                    self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                                           trade_time=exit_date,
                                                                           profit_loss=profit_loss,
                                                                           instrument_token=
                                                                           self.index_data_management.index[
                                                                               'instrument_token'],
                                                                           average_exit_price=average_exit_price)
                                    self.record_trade(active_trade['signal'], active_trade['entry_price'], exit_price,
                                                      profit_loss, quantity, result,
                                                      active_trade['stoploss_price'], exit_date,
                                                      average_entry_price, average_exit_price)
                                    logger.info(
                                        f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                                    self.webSocketManager.unsubscribe([active_trade['signal']['instrument_token']])
                                    try:
                                        self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure,\nIndex: {index_details['tradingsymbol']},\nStrike: {active_trade['signal']['symbol']}")
                                    except Exception as whatsappException:
                                        self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure. Whatsapp Message also failed due to argument error.")

                                    # play_help_siren_threaded()
                    else:
                        logger.info(f"Current stoploss price is less than previous stoploss. Hence, not updated")

            logger.info("Completed execution loop of updating stoploss & target")
            logger.info("Active trade")
            logger.info(self.trade_manager.active_trades)
            logger.info("Closed trade")
            logger.info(self.trade_manager.closed_trades)
        except Exception as e:
            logger.info("Error occurred while updating stoploss order" + e)

    # def sellTrade(self, last_option_data, entry_price, target_price, instrument_token, quantity,active_trade_data):
    #     current_price = last_option_data['close']
    #     stoploss_price = last_option_data['stoploss']
    #     exit_price = None
    #     result = None
    #
    #     logger.info("Attempting to sell trade...")
    #
    #     if current_price <= stoploss_price:
    #         exit_price = stoploss_price if current_price <= entry_price else current_price
    #         exit_date = last_option_data['date']
    #         result = "Stopped out"
    #         logger.info(f"Stopped out at {exit_price} on {exit_date}")
    #         profit_loss = (exit_price - entry_price) * quantity
    #         self.trade_manager.update_trade_status(trade_type='SELL', result=result, trade_time=exit_date,
    #                                                profit_loss=profit_loss,
    #                                                instrument_token=instrument_token)
    #         self.record_trade(active_trade_data['signal'], entry_price, exit_price, profit_loss, quantity, result, stoploss_price, exit_date)
    #     elif current_price >= target_price:
    #         exit_price = current_price
    #         exit_date = last_option_data['date']
    #         result = "Target reached"
    #         logger.info(f"Target reached at {exit_price} on {exit_date}")
    #         profit_loss = (exit_price - entry_price) * quantity
    #         self.trade_manager.update_trade_status(trade_type='SELL', result=result, trade_time=exit_date,
    #                                                profit_loss=profit_loss,
    #                                                instrument_token=instrument_token)
    #         self.record_trade(active_trade_data['signal'], entry_price, exit_price, profit_loss, quantity, result, stoploss_price, exit_date)
    #
    #     elif pd.to_datetime(last_option_data['date']).time() >= datetime.time(15, 30):  # Check if it's post 3:30 PM
    #         exit_price = last_option_data['close']
    #         exit_date = last_option_data['date']
    #         result = "Exited at 2:30 PM"
    #         profit_loss = (exit_price - entry_price) * quantity
    #         logger.info(f"Exited at 2:30 PM at {exit_price} on {exit_date}")
    #         self.trade_manager.update_trade_status(trade_type='SELL', result=result, trade_time=exit_date,
    #                                                profit_loss=profit_loss,
    #                                                instrument_token=instrument_token)
    #         self.record_trade(active_trade_data['signal'], entry_price, exit_price, profit_loss, quantity, result, stoploss_price, exit_date)
    #
    #     logger.info("Active trade")
    #     logger.info(self.trade_manager.active_trades)
    #     logger.info("Closed trade")
    #     logger.info(self.trade_manager.closed_trades)

    def cancel_order(self, order_id):
        try:
            return self.kite.cancel_order(variety="regular", order_id=order_id)
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return None

    def modify_order(self, order_id, variety, order_type=None,price=None, trigger_price=None):
        try:
            return self.kite.modify_order(
                variety=variety,
                order_id=order_id,
                price=self.round_to_tick_size(price),
                trigger_price=self.round_to_tick_size(trigger_price),
                order_type=order_type
            )
        except Exception as e:
            logger.error(f"Error modifying order: {e}")
            return None

    def sell_trade_on_ltp_update(self, instrument_token, ltp):
        logger.info(f"Updated LTP received as {ltp} for Instrument Token as {instrument_token} . Time to check if Sell Trade is possible")
        index_instrument_token = self.index_data_management.index['instrument_token']
        index_details = self.index_data_management.index
        if self.processing:
            logger.info(f"LTP has been rejected as Sell Trade process is already ongoing.")
            return

        self.processing = True
        logger.info(f"LTP has been accepted to check for Sell Trade Possibility.")
        try:
            active_trade = self.trade_manager.get_active_trade(index_instrument_token)
            if not active_trade:
                self.processing = False
                logger.info(f"No Active trade found for Index Instrument Token: {index_instrument_token}")
                return
            logger.info(f"Active trade found for index instrument token: {index_instrument_token}")
            target_price = active_trade['target_price']
            stoploss_price = active_trade['stoploss_price']
            sl_order_id = active_trade['sl_order_id']

            if ltp >= target_price:
                logger.info("LTP is now greater than Target Price. Modifying Stoploss Order to Sell Order Market")
                for _ in range(5):
                    if self.modify_order(sl_order_id, "regular", order_type="MARKET") is not None:
                        logger.info(f"Attempt {_} : Modified SL Limit Order to Sell Market order successfully")
                        sell_order_id = sl_order_id
                        logger.info(f"Attempt {_} : Sell order placed with order id {sell_order_id}")
                        while True:
                            logger.info(f"Attempt {_} : Checking the status of sell order id {sell_order_id}")
                            orderHistory = self.check_order(sell_order_id)
                            logger.info(f"Attempt {_} : Checked the status of sell order id {sell_order_id} with status as {orderHistory['status']}")
                            status = orderHistory['status']
                            if status == "COMPLETE":
                                logger.info(f"Attempt {_} : Checked the status of completed sell order id {sell_order_id} with status as {orderHistory['status']}")
                                average_exit_price = orderHistory['average_price']
                                exit_price = ltp
                                result = "Target reached"
                                ist = pytz.timezone('Asia/Kolkata')
                                exit_datetime_obj = datetime.strptime(
                                    orderHistory['exchange_update_timestamp'], "%Y-%m-%d %H:%M:%S")
                                exit_datetime_obj_ist = ist.localize(exit_datetime_obj)
                                exit_date = exit_datetime_obj_ist
                                average_entry_price = active_trade['average_entry_price']
                                quantity = active_trade['quantity']
                                profit_loss = (average_exit_price - average_entry_price) * quantity
                                self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                                       trade_time=exit_date,
                                                                       profit_loss=profit_loss,
                                                                       instrument_token=index_instrument_token,
                                                                       average_exit_price=average_exit_price)
                                self.record_trade(active_trade['signal'], active_trade['entry_price'], exit_price,
                                                  profit_loss, quantity, result,
                                                  active_trade['stoploss_price'], exit_date,
                                                  average_entry_price, average_exit_price)
                                logger.info(f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                                self.webSocketManager.unsubscribe([active_trade['signal']['instrument_token']])
                                try:
                                    self.send_whatsapp_message(f"Trade Exited...\nBuying Algo,\nResult: {result},\nStrike: {active_trade['signal']['symbol']},\nIndex: {index_details['tradingsymbol']},\nEntry Time: {active_trade['actual_entry_date']},\nExit Time: {exit_date},\nEntry Price: {active_trade['entry_price']},\nActual Entry Price: {active_trade['average_entry_price']},\nActual Exit Price: {average_exit_price},\nP&L = {profit_loss}")
                                except Exception as whatsappException:
                                    self.send_whatsapp_message(f"Buying Algo,\nA Trade was Completed but Whatsapp Message failed due to argument error.")
                                break
                            elif status in self.failureTerminatedOrderStatus:
                                logger.info(f"Attempt {_} : Checked the status of failed sell order id {sell_order_id} with status as {orderHistory['status']}")
                                logger.info(f"Attempt {_} : Sell Order also failed after SL order failure, so calling, emailing Dagar and raising alarm siren")
                                average_exit_price = ltp
                                result = "Stopped out"
                                exit_date = datetime.now()
                                average_entry_price = active_trade['average_entry_price']
                                quantity = active_trade['quantity']
                                exit_price = active_trade['stoploss_price']
                                profit_loss = (average_exit_price - average_entry_price) * quantity
                                self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                                       trade_time=exit_date,
                                                                       profit_loss=profit_loss,
                                                                       instrument_token=
                                                                       self.index_data_management.index[
                                                                           'instrument_token'],
                                                                       average_exit_price=average_exit_price)
                                self.record_trade(active_trade['signal'], active_trade['entry_price'], exit_price,
                                                  profit_loss, quantity, result,
                                                  active_trade['stoploss_price'], exit_date,
                                                  average_entry_price, average_exit_price)
                                logger.info(
                                    f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                                self.webSocketManager.unsubscribe([active_trade['signal']['instrument_token']])
                                try:
                                    self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure,\nIndex: {index_details['tradingsymbol']},\nStrike: {active_trade['signal']['symbol']}")
                                except Exception as whatsappException:
                                    self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure. Whatsapp Message also failed due to argument error.")

                                # play_help_siren_threaded()
                                break
                            else:
                                logger.info(f"Attempt {_} : Checked the status of sell order id {sell_order_id} with status as {orderHistory['status']}")
                        logger.info(f"Reached to selling last step when SL modification to sell market order successful.")
                        break
                    else:
                        logger.info(f"Attempt {_} : Not been able to modify SL limit order to  sell market order. so retrying")
                else:
                    logger.info(f"SL Limit Modify order failed 5 times. Now Time to cancel this SL limit order and place a fresh Market Sell Order")
                    cancelled_sl_order_id = self.cancel_order(sl_order_id)
                    if cancelled_sl_order_id is None:
                        logger.info(f"Could not cancel sl order")
                        logger.info(f"Cancel Order failed, so calling, emailing Dagar and raising alarm siren")
                        average_exit_price = ltp
                        result = "Stopped out"
                        exit_date = datetime.now()
                        average_entry_price = active_trade['average_entry_price']
                        quantity = active_trade['quantity']
                        exit_price = active_trade['stoploss_price']
                        profit_loss = (average_exit_price - average_entry_price) * quantity
                        self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                               trade_time=exit_date,
                                                               profit_loss=profit_loss,
                                                               instrument_token=
                                                               self.index_data_management.index[
                                                                   'instrument_token'],
                                                               average_exit_price=average_exit_price)
                        self.record_trade(active_trade['signal'], active_trade['entry_price'], exit_price,
                                          profit_loss, quantity, result,
                                          active_trade['stoploss_price'], exit_date,
                                          average_entry_price, average_exit_price)
                        logger.info(
                            f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                        self.webSocketManager.unsubscribe([active_trade['signal']['instrument_token']])
                        try:
                            self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSL modify failed and SL cancel also failed. Exit the trade manually.\nIndex: {index_details['tradingsymbol']},\nStrike: {active_trade['signal']['symbol']}")
                        except Exception as whatsappException:
                            self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSL modify failed and SL cancel also failed. Exit the trade manually. Whatsapp Message also failed due to argument error.")

                        # play_help_siren_threaded()
                    else:
                        logger.info(f"Cancelled sl order. Now placing sell market order")
                        for _ in range(5):
                            logger.info(f"Attempt {_} : Placing sell order tradingsymbol : {active_trade['signal']['instrument']['tradingsymbol']} quantity : {active_trade['quantity']}")
                            sell_order_id = self.place_order(
                                variety="regular",
                                tradingsymbol=active_trade['signal']['instrument']['tradingsymbol'],
                                exchange="NFO",
                                transaction_type="SELL",
                                order_type="MARKET",
                                quantity=active_trade['quantity'],
                                product="MIS",
                                validity="DAY"
                            )
                            if sell_order_id:
                                logger.info(f"Attempt {_} : Sell order placed with order id {sell_order_id}")
                                while True:
                                    logger.info(f"Attempt {_} : Checking the status of sell order id {sell_order_id}")
                                    orderHistory = self.check_order(sell_order_id)
                                    logger.info(f"Attempt {_} : Checked the status of sell order id {sell_order_id} with status as {orderHistory['status']}")
                                    status = orderHistory['status']
                                    if status == "COMPLETE":
                                        logger.info(f"Attempt {_} : Checked the status of completed sell order id {sell_order_id} with status as {orderHistory['status']}")
                                        average_exit_price = orderHistory['average_price']
                                        exit_price = ltp
                                        result = "Target reached"
                                        ist = pytz.timezone('Asia/Kolkata')
                                        exit_datetime_obj = datetime.strptime(
                                            orderHistory['exchange_update_timestamp'], "%Y-%m-%d %H:%M:%S")
                                        exit_datetime_obj_ist = ist.localize(exit_datetime_obj)
                                        exit_date = exit_datetime_obj_ist
                                        average_entry_price = active_trade['average_entry_price']
                                        quantity = active_trade['quantity']
                                        profit_loss = (average_exit_price - average_entry_price) * quantity
                                        self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                                               trade_time=exit_date,
                                                                               profit_loss=profit_loss,
                                                                               instrument_token=index_instrument_token,
                                                                               average_exit_price=average_exit_price)
                                        self.record_trade(active_trade['signal'], active_trade['entry_price'], exit_price,
                                                          profit_loss, quantity, result,
                                                          active_trade['stoploss_price'], exit_date,
                                                          average_entry_price, average_exit_price)
                                        logger.info(
                                            f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                                        self.webSocketManager.unsubscribe([active_trade['signal']['instrument_token']])
                                        try:
                                            self.send_whatsapp_message(f"Trade Exited...\nBuying Algo,\nResult: {result},\nStrike: {active_trade['signal']['symbol']},\nIndex: {index_details['tradingsymbol']},\nEntry Time: {active_trade['actual_entry_date']},\nExit Time: {exit_date},\nEntry Price: {active_trade['entry_price']},\nActual Entry Price: {active_trade['average_entry_price']},\nActual Exit Price: {average_exit_price},\nP&L = {profit_loss}")
                                        except Exception as whatsappException:
                                            self.send_whatsapp_message(f"Buying Algo,\nA Trade was Completed but Whatsapp Message failed due to argument error.")
                                        break
                                    elif status in self.failureTerminatedOrderStatus:
                                        logger.info(f"Attempt {_} : Checked the status of failed sell order id {sell_order_id} with status as {orderHistory['status']}")
                                        logger.info(f"Attempt {_} : Sell Order also failed after SL order failure, so calling, emailing Dagar and raising alarm siren")
                                        average_exit_price = ltp
                                        result = "Stopped out"
                                        exit_date = datetime.now()
                                        average_entry_price = active_trade['average_entry_price']
                                        quantity = active_trade['quantity']
                                        exit_price = active_trade['stoploss_price']
                                        profit_loss = (average_exit_price - average_entry_price) * quantity
                                        self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                                               trade_time=exit_date,
                                                                               profit_loss=profit_loss,
                                                                               instrument_token=
                                                                               self.index_data_management.index[
                                                                                   'instrument_token'],
                                                                               average_exit_price=average_exit_price)
                                        self.record_trade(active_trade['signal'], active_trade['entry_price'],
                                                          exit_price,
                                                          profit_loss, quantity, result,
                                                          active_trade['stoploss_price'], exit_date,
                                                          average_entry_price, average_exit_price)
                                        logger.info(
                                            f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                                        self.webSocketManager.unsubscribe([active_trade['signal']['instrument_token']])
                                        try:
                                            self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure,\nIndex: {index_details['tradingsymbol']},\nStrike: {active_trade['signal']['symbol']}")
                                        except Exception as whatsappException:
                                            self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure. Whatsapp Message also failed due to argument error.")

                                        # play_help_siren_threaded()
                                        break
                                    else:
                                        logger.info(f"Attempt {_} : Checked the status of sell order id {sell_order_id} with status as {orderHistory['status']}")
                                logger.info(f"Reached to selling last step when SL modification failed.")
                                break
                            else:
                                logger.info(f"Attempt {_} : Not been able to place sell order. so retrying")
                        else:
                            logger.info(f"Attempts exhausted : Not able to place sell order, so calling, emailing, whatsapp Dagar and raising alarm siren")
                            average_exit_price = ltp
                            result = "Stopped out"
                            exit_date = datetime.now()
                            average_entry_price = active_trade['average_entry_price']
                            quantity = active_trade['quantity']
                            exit_price = active_trade['stoploss_price']
                            profit_loss = (average_exit_price - average_entry_price) * quantity
                            self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                                   trade_time=exit_date,
                                                                   profit_loss=profit_loss,
                                                                   instrument_token=
                                                                   self.index_data_management.index[
                                                                       'instrument_token'],
                                                                   average_exit_price=average_exit_price)
                            self.record_trade(active_trade['signal'], active_trade['entry_price'], exit_price,
                                              profit_loss, quantity, result,
                                              active_trade['stoploss_price'], exit_date,
                                              average_entry_price, average_exit_price)
                            logger.info(
                                f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                            self.webSocketManager.unsubscribe([active_trade['signal']['instrument_token']])
                            try:
                                self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure,\nIndex: {index_details['tradingsymbol']},\nStrike: {active_trade['signal']['symbol']}")
                            except Exception as whatsappException:
                                self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure. Whatsapp Message also failed due to argument error.")

                            # play_help_siren_threaded()
            elif ltp < stoploss_price or datetime.now().time() >= time(14, 30):
                ltpSmaller = ltp < stoploss_price
                timePassed = datetime.now().time() >= time(14, 30)
                if ltpSmaller:
                    logger.info(f"LTP is now smaller than stoploss price. Checking stoploss order status")
                elif timePassed:
                    logger.info(f"Current Time has passed 2:30 PM. Checking stoploss order status. If not completed, we will place sell market order")
                orderHistory = self.check_order(sl_order_id)
                logger.info(f"Checked the status of stoploss order id {sl_order_id} with status as {orderHistory['status']}")
                status = orderHistory['status']
                if status == "COMPLETE":
                    logger.info(f"Checked the status of completed stoploss order id {sl_order_id} with status as {orderHistory['status']}")
                    average_exit_price = orderHistory['average_price']
                    result = "Stopped out"
                    ist = pytz.timezone('Asia/Kolkata')
                    exit_datetime_obj = datetime.strptime(
                        orderHistory['exchange_update_timestamp'], "%Y-%m-%d %H:%M:%S")
                    exit_datetime_obj_ist = ist.localize(exit_datetime_obj)
                    exit_date = exit_datetime_obj_ist
                    average_entry_price = active_trade['average_entry_price']
                    quantity = active_trade['quantity']
                    exit_price = active_trade['stoploss_price']
                    profit_loss = (average_exit_price - average_entry_price) * quantity
                    self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                           trade_time=exit_date,
                                                           profit_loss=profit_loss,
                                                           instrument_token=
                                                           self.index_data_management.index[
                                                               'instrument_token'],
                                                           average_exit_price=average_exit_price)
                    self.record_trade(active_trade['signal'], active_trade['entry_price'], exit_price,
                                      profit_loss, quantity, result,
                                      active_trade['stoploss_price'], exit_date,
                                      average_entry_price, average_exit_price)
                    logger.info(
                        f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                    self.webSocketManager.unsubscribe([instrument_token])
                    try:
                        self.send_whatsapp_message(f"Trade Exited...\nBuying Algo,\nResult: {result},\nStrike: {active_trade['signal']['symbol']},\nIndex: {index_details['tradingsymbol']},\nEntry Time: {active_trade['actual_entry_date']},\nExit Time: {exit_date},\nEntry Price: {active_trade['entry_price']},\nActual Entry Price: {active_trade['average_entry_price']},\nActual Exit Price: {average_exit_price},\nP&L = {profit_loss}")
                    except Exception as whatsappException:
                        self.send_whatsapp_message(f"Buying Algo,\nA Trade was Completed but Whatsapp Message failed due to argument error.")
                elif status in self.failureTerminatedOrderStatus:
                    logger.info(f"A SL modification failed as SL was cancelled previously. Manually Verify once that this Trade has been exited.,\nStrike: {active_trade['signal']['symbol']},\nIndex: {index_details['tradingsymbol']}")
                    average_exit_price = ltp
                    result = "Stopped out"
                    exit_date = datetime.now()
                    average_entry_price = active_trade['average_entry_price']
                    quantity = active_trade['quantity']
                    exit_price = active_trade['stoploss_price']
                    profit_loss = (average_exit_price - average_entry_price) * quantity
                    self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                           trade_time=exit_date,
                                                           profit_loss=profit_loss,
                                                           instrument_token=
                                                           self.index_data_management.index[
                                                               'instrument_token'],
                                                           average_exit_price=average_exit_price)
                    self.record_trade(active_trade['signal'], active_trade['entry_price'], exit_price,
                                      profit_loss, quantity, result,
                                      active_trade['stoploss_price'], exit_date,
                                      average_entry_price, average_exit_price)
                    logger.info(
                        f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                    self.webSocketManager.unsubscribe([active_trade['signal']['instrument_token']])
                    try:
                        self.send_whatsapp_message(f"A SL modification failed as SL was cancelled previously. Manually Verify once that this Trade has been exited.,\nStrike: {active_trade['signal']['symbol']},\nIndex: {index_details['tradingsymbol']}")
                    except Exception as whatsappException:
                        self.send_whatsapp_message(f"Buying Algo,\nA SL modification failed as SL was cancelled previously. Manually Verify once that this Trade has been exited. but Whatsapp Message failed due to argument error.")
                else:
                    for _ in range(5):
                        if self.modify_order(sl_order_id, "regular", order_type="MARKET") is not None:
                            logger.info(f"Modified SL Limit Order to Sell Market order successfully")
                            sell_order_id = sl_order_id
                            logger.info(f"Attempt {_} : Sell order placed with order id {sell_order_id}")
                            while True:
                                logger.info(f"Attempt {_} : Checking the status of sell order id {sell_order_id}")
                                orderHistory = self.check_order(sell_order_id)
                                logger.info(
                                    f"Attempt {_} : Checked the status of sell order id {sell_order_id} with status as {orderHistory['status']}")
                                status = orderHistory['status']
                                if status == "COMPLETE":
                                    logger.info(f"Attempt {_} : Checked the status of completed sell order id {sell_order_id} with status as {orderHistory['status']}")
                                    average_exit_price = orderHistory['average_price']
                                    exit_price = ltp
                                    if ltpSmaller:
                                        result = "Stopped out"
                                    elif timePassed:
                                        result = "Exited at 2:30 PM"
                                    ist = pytz.timezone('Asia/Kolkata')
                                    exit_datetime_obj = datetime.strptime(
                                        orderHistory['exchange_update_timestamp'], "%Y-%m-%d %H:%M:%S")
                                    exit_datetime_obj_ist = ist.localize(exit_datetime_obj)
                                    exit_date = exit_datetime_obj_ist
                                    average_entry_price = active_trade['average_entry_price']
                                    quantity = active_trade['quantity']
                                    profit_loss = (average_exit_price - average_entry_price) * quantity
                                    self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                                           trade_time=exit_date,
                                                                           profit_loss=profit_loss,
                                                                           instrument_token=index_instrument_token,
                                                                           average_exit_price=average_exit_price)
                                    self.record_trade(active_trade['signal'], active_trade['entry_price'], exit_price,
                                                      profit_loss, quantity, result,
                                                      active_trade['stoploss_price'], exit_date,
                                                      average_entry_price, average_exit_price)
                                    logger.info(f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                                    self.webSocketManager.unsubscribe([active_trade['signal']['instrument_token']])
                                    try:
                                        self.send_whatsapp_message(f"Trade Exited...\nBuying Algo,\nResult: {result},\nStrike: {active_trade['signal']['symbol']},\nIndex: {index_details['tradingsymbol']},\nEntry Time: {active_trade['actual_entry_date']},\nExit Time: {exit_date},\nEntry Price: {active_trade['entry_price']},\nActual Entry Price: {active_trade['average_entry_price']},\nActual Exit Price: {average_exit_price},\nP&L = {profit_loss}")
                                    except Exception as whatsappException:
                                        self.send_whatsapp_message(f"Buying Algo,\nA Trade was Completed but Whatsapp Message failed due to argument error.")
                                    break
                                elif status in self.failureTerminatedOrderStatus:
                                    logger.info(f"Attempt {_} : Checked the status of failed sell order id {sell_order_id} with status as {orderHistory['status']}")
                                    logger.info(f"Attempt {_} : Sell Order also failed after SL order failure, so calling, emailing Dagar and raising alarm siren")
                                    average_exit_price = ltp
                                    result = "Stopped out"
                                    exit_date = datetime.now()
                                    average_entry_price = active_trade['average_entry_price']
                                    quantity = active_trade['quantity']
                                    exit_price = active_trade['stoploss_price']
                                    profit_loss = (average_exit_price - average_entry_price) * quantity
                                    self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                                           trade_time=exit_date,
                                                                           profit_loss=profit_loss,
                                                                           instrument_token=
                                                                           self.index_data_management.index[
                                                                               'instrument_token'],
                                                                           average_exit_price=average_exit_price)
                                    self.record_trade(active_trade['signal'], active_trade['entry_price'], exit_price,
                                                      profit_loss, quantity, result,
                                                      active_trade['stoploss_price'], exit_date,
                                                      average_entry_price, average_exit_price)
                                    logger.info(
                                        f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                                    self.webSocketManager.unsubscribe([active_trade['signal']['instrument_token']])
                                    try:
                                        self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure,\nIndex: {index_details['tradingsymbol']},\nStrike: {active_trade['signal']['symbol']}")
                                    except Exception as whatsappException:
                                        self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure. Whatsapp Message also failed due to argument error.")

                                    # play_help_siren_threaded()
                                    break
                                else:
                                    logger.info(f"Attempt {_} : Checked the status of sell order id {sell_order_id} with status as {orderHistory['status']}")
                            logger.info(f"Reached to selling last step when SL modification to sell market order successful.")
                            break
                        else:
                            logger.info(f"Attempt {_} : Not been able to modify SL limit order to  sell market order. so retrying")
                    else:
                        logger.info(f"SL Limit Modify order failed 5 times. Now Time to cancel this SL limit order and place a fresh Market Sell Order")
                        cancelled_sl_order_id = self.cancel_order(sl_order_id)
                        if cancelled_sl_order_id is None:
                            logger.info(f"Could not cancel sl order")
                            logger.info(f"Cancel Order failed, so calling, emailing Dagar and raising alarm siren")
                            average_exit_price = ltp
                            result = "Stopped out"
                            exit_date = datetime.now()
                            average_entry_price = active_trade['average_entry_price']
                            quantity = active_trade['quantity']
                            exit_price = active_trade['stoploss_price']
                            profit_loss = (average_exit_price - average_entry_price) * quantity
                            self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                                   trade_time=exit_date,
                                                                   profit_loss=profit_loss,
                                                                   instrument_token=
                                                                   self.index_data_management.index[
                                                                       'instrument_token'],
                                                                   average_exit_price=average_exit_price)
                            self.record_trade(active_trade['signal'], active_trade['entry_price'], exit_price,
                                              profit_loss, quantity, result,
                                              active_trade['stoploss_price'], exit_date,
                                              average_entry_price, average_exit_price)
                            logger.info(
                                f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                            self.webSocketManager.unsubscribe([active_trade['signal']['instrument_token']])
                            try:
                                self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSL modify failed and SL cancel also failed. Exit the trade manually.\nIndex: {index_details['tradingsymbol']},\nStrike: {active_trade['signal']['symbol']}")
                            except Exception as whatsappException:
                                self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSL modify failed and SL cancel also failed. Exit the trade manually. Whatsapp Message also failed due to argument error.")
                            # play_help_siren_threaded()
                        else:
                            logger.info(f"Cancelled sl order. Now placing sell market order")
                            for _ in range(5):
                                logger.info(f"Attempt {_} : Placing sell order tradingsymbol : {active_trade['signal']['instrument']['tradingsymbol']} quantity : {active_trade['quantity']}")
                                sell_order_id = self.place_order(
                                    variety="regular",
                                    tradingsymbol=active_trade['signal']['instrument']['tradingsymbol'],
                                    exchange="NFO",
                                    transaction_type="SELL",
                                    order_type="MARKET",
                                    quantity=active_trade['quantity'],
                                    product="MIS",
                                    validity="DAY"
                                )
                                if sell_order_id:
                                    logger.info(f"Attempt {_} : Sell order placed with order id {sell_order_id}")
                                    while True:
                                        logger.info(f"Attempt {_} : Checking the status of sell order id {sell_order_id}")
                                        orderHistory = self.check_order(sell_order_id)
                                        logger.info(f"Attempt {_} : Checked the status of sell order id {sell_order_id} with status as {orderHistory['status']}")
                                        status = orderHistory['status']
                                        if status == "COMPLETE":
                                            logger.info(f"Attempt {_} : Checked the status of completed sell order id {sell_order_id} with status as {orderHistory['status']}")
                                            average_exit_price = orderHistory['average_price']
                                            exit_price = ltp
                                            if ltpSmaller:
                                                result = "Stopped out"
                                            elif timePassed:
                                                result = "Exited at 2:30 PM"
                                            ist = pytz.timezone('Asia/Kolkata')
                                            exit_datetime_obj = datetime.strptime(
                                                orderHistory['exchange_update_timestamp'], "%Y-%m-%d %H:%M:%S")
                                            exit_datetime_obj_ist = ist.localize(exit_datetime_obj)
                                            exit_date = exit_datetime_obj_ist
                                            average_entry_price = active_trade['average_entry_price']
                                            quantity = active_trade['quantity']
                                            profit_loss = (average_exit_price - average_entry_price) * quantity
                                            self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                                                   trade_time=exit_date,
                                                                                   profit_loss=profit_loss,
                                                                                   instrument_token=index_instrument_token,
                                                                                   average_exit_price=average_exit_price)
                                            self.record_trade(active_trade['signal'], active_trade['entry_price'],
                                                              exit_price,
                                                              profit_loss, quantity, result,
                                                              active_trade['stoploss_price'], exit_date,
                                                              average_entry_price, average_exit_price)
                                            logger.info(f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                                            self.webSocketManager.unsubscribe(
                                                [active_trade['signal']['instrument_token']])
                                            try:
                                                self.send_whatsapp_message(f"Trade Exited...\nBuying Algo,\nResult: {result},\nStrike: {active_trade['signal']['symbol']},\nIndex: {index_details['tradingsymbol']},\nEntry Time: {active_trade['actual_entry_date']},\nExit Time: {exit_date},\nEntry Price: {active_trade['entry_price']},\nActual Entry Price: {active_trade['average_entry_price']},\nActual Exit Price: {average_exit_price},\nP&L = {profit_loss}")
                                            except Exception as whatsappException:
                                                self.send_whatsapp_message(f"Buying Algo,\nA Trade was Completed but Whatsapp Message failed due to argument error.")
                                            break
                                        elif status in self.failureTerminatedOrderStatus:
                                            logger.info(f"Attempt {_} : Checked the status of failed sell order id {sell_order_id} with status as {orderHistory['status']}")
                                            logger.info(f"Attempt {_} : Sell Order also failed after SL order failure, so calling, emailing Dagar and raising alarm siren")
                                            average_exit_price = ltp
                                            result = "Stopped out"
                                            exit_date = datetime.now()
                                            average_entry_price = active_trade['average_entry_price']
                                            quantity = active_trade['quantity']
                                            exit_price = active_trade['stoploss_price']
                                            profit_loss = (average_exit_price - average_entry_price) * quantity
                                            self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                                                   trade_time=exit_date,
                                                                                   profit_loss=profit_loss,
                                                                                   instrument_token=
                                                                                   self.index_data_management.index[
                                                                                       'instrument_token'],
                                                                                   average_exit_price=average_exit_price)
                                            self.record_trade(active_trade['signal'], active_trade['entry_price'],
                                                              exit_price,
                                                              profit_loss, quantity, result,
                                                              active_trade['stoploss_price'], exit_date,
                                                              average_entry_price, average_exit_price)
                                            logger.info(
                                                f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                                            self.webSocketManager.unsubscribe(
                                                [active_trade['signal']['instrument_token']])
                                            try:
                                                self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure,\nIndex: {index_details['tradingsymbol']},\nStrike: {active_trade['signal']['symbol']}")
                                            except Exception as whatsappException:
                                                self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure. Whatsapp Message also failed due to argument error.")

                                            # play_help_siren_threaded()
                                            break
                                        else:
                                            logger.info(f"Attempt {_} : Checked the status of sell order id {sell_order_id} with status as {orderHistory['status']}")
                                    logger.info(f"Reached to selling last step when SL modification failed.")
                                    break
                                else:
                                    logger.info(f"Attempt {_} : Not been able to place sell order. so retrying")
                            else:
                                logger.info(f"Attempts exhausted : Not able to place sell order, so calling, emailing, whatsapp Dagar and raising alarm siren")
                                average_exit_price = ltp
                                result = "Stopped out"
                                exit_date = datetime.now()
                                average_entry_price = active_trade['average_entry_price']
                                quantity = active_trade['quantity']
                                exit_price = active_trade['stoploss_price']
                                profit_loss = (average_exit_price - average_entry_price) * quantity
                                self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                                       trade_time=exit_date,
                                                                       profit_loss=profit_loss,
                                                                       instrument_token=
                                                                       self.index_data_management.index[
                                                                           'instrument_token'],
                                                                       average_exit_price=average_exit_price)
                                self.record_trade(active_trade['signal'], active_trade['entry_price'], exit_price,
                                                  profit_loss, quantity, result,
                                                  active_trade['stoploss_price'], exit_date,
                                                  average_entry_price, average_exit_price)
                                logger.info(
                                    f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                                self.webSocketManager.unsubscribe([active_trade['signal']['instrument_token']])
                                try:
                                    self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure,\nIndex: {index_details['tradingsymbol']},\nStrike: {active_trade['signal']['symbol']}")
                                except Exception as whatsappException:
                                    self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure. Whatsapp Message also failed due to argument error.")

                                # play_help_siren_threaded()
            else:
                logger.info(f"Sell trade conditions not met yet")
        except Exception as sellTradeException:
            logger.error(f"Exception ocurred while selling trade on websocket for LTP received as {ltp} for Instrument Token as {instrument_token} . Exception : {sellTradeException}")
        finally:
            self.processing = False

        logger.info("Active trade")
        logger.info(self.trade_manager.active_trades)
        logger.info("Closed trade")
        logger.info(self.trade_manager.closed_trades)

    def fetch_ltp(self, instrument_token):
        logger.info(f"Fetching ltp for {instrument_token}")
        try:
            ltp_data = self.kite.ltp([instrument_token])
            return ltp_data[instrument_token]['last_price']
        except Exception as e:
            logger.error(f"Error fetching LTP: {e}")
            return None

    def place_order(self, variety, exchange, tradingsymbol, transaction_type, quantity, order_type='MARKET',
                    product='MIS', validity='DAY',trigger_price=None,price=None):
        try:
            order_id = self.kite.place_order(
                variety=variety,
                exchange=exchange,
                tradingsymbol=tradingsymbol,
                transaction_type=transaction_type,
                quantity=quantity,
                order_type=order_type,
                product=product,
                validity=validity,
                trigger_price=trigger_price,
                price=price
            )
            return order_id
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None

    def check_order(self, order_id):
        try:
            order_status = self.kite.order_history(order_id)
            return order_status[-1]
        except Exception as e:
            logger.error(f"Error checking order status: {e}")
            return None


    def round_to_tick_size(self, value):
        """Round the value to the nearest tick size."""
        if value is None:
            return value
        return round(value / self.config['tick_size']) * self.config['tick_size']

    @staticmethod
    def round_to_tick_size_static(value,tick_size):
        """Round the value to the nearest tick size."""
        return round(value / tick_size) * tick_size

    def place_sl_order(self, tradingsymbol, quantity, stoploss_trigger_price):
        try:

            return self.place_order(
                variety="regular",
                tradingsymbol=tradingsymbol,
                exchange="NFO",
                transaction_type="SELL",
                order_type="SL",
                trigger_price= self.round_to_tick_size(stoploss_trigger_price),
                price = self.round_to_tick_size(stoploss_trigger_price* 0.98),
                quantity=quantity,
                product="MIS",
                validity="DAY"
            )
        except Exception as e:
            logger.error(f"Error placing sl order: {e}")
            return None

    # def buyTrade(self, signal, option_data, index):
    #     option_data = option_data.iloc[-1]
    #     entry_price = option_data['close']
    #     lot_size = self.config['INDEX_DETAILS'][self.config['current_index']]['lot_size']
    #     quantity = self.config['TRADE_SIZE'] // (entry_price * lot_size) * lot_size
    #     target_price = option_data['target_price']
    #     stoploss_price = option_data['stoploss']
    #
    #     self.trade_manager.register_trade(signal['type'], signal['date'], index['instrument_token'], signal, entry_price, lot_size, quantity, target_price, stoploss_price, option_data['rsi'])
    #     self.record_trade(signal, entry_price, None, 0, quantity, "Open", stoploss_price, None)
    #     logger.info(f"Bought trade... Entry Price: {entry_price}, Lot Size: {lot_size}, Quantity: {quantity}, Target Price: {target_price}, Stoploss Price: {stoploss_price}")
    #     logger.info("Active trade")
    #     logger.info(self.trade_manager.active_trades)
    #     logger.info("Closed trade")
    #     logger.info(self.trade_manager.closed_trades)

    def buyTrade(self, signal, option_data, index):
        start_time = datetime.now()
        option_data = option_data.iloc[-1]
        entry_price = option_data['close']
        lot_size = self.config['INDEX_DETAILS'][self.config['current_index']]['lot_size']
        quantity = int(self.config['TRADE_SIZE'] // (entry_price * lot_size) * lot_size)
        target_price = option_data['target_price']
        stoploss_price = option_data['stoploss']

        while (datetime.now() - start_time).seconds < 59:
            logger.info(f"Fetching ltp for {signal['instrument']['instrument_token']}")
            ltp = self.fetch_ltp(f"{signal['instrument']['exchange']}:{signal['instrument']['tradingsymbol']}")
            if ltp is None:
                logger.info(f"Fetched ltp is None")
                continue
            logger.info(f"Fetched ltp is {ltp}")
            if ltp  <= (1.08 * entry_price):
                logger.info(f"Placing buy order at ltp {ltp}")
                order_id = self.place_order(
                    variety="regular",
                    tradingsymbol=signal['instrument']['tradingsymbol'],
                    exchange="NFO",
                    transaction_type="BUY",
                    order_type="MARKET",
                    quantity=quantity,
                    product="MIS",
                    validity="DAY"
                )
                if order_id:
                    # play_bought_siren_threaded()
                    logger.info(f"Buy Order placed with order id {order_id}")
                    while True:
                        logger.info(f"Checking the status of buy order id {order_id}")
                        orderHistory = self.check_order(order_id)
                        logger.info(f"Checked the status of buy order id {order_id} with status as {orderHistory['status']}")
                        status = orderHistory['status']
                        if status == "COMPLETE":
                            logger.info(f"Buy order is completed with order id {order_id} and status as {orderHistory['status']}")
                            average_entry_price = orderHistory['average_price']
                            ist = pytz.timezone('Asia/Kolkata')
                            entry_datetime_obj = datetime.strptime(orderHistory['exchange_update_timestamp'],
                                                                  "%Y-%m-%d %H:%M:%S")
                            entry_datetime_obj_ist = ist.localize(entry_datetime_obj)
                            actual_entry_date = entry_datetime_obj_ist
                            self.trade_manager.register_trade(signal['type'], signal['date'], index['instrument_token'],
                                                              signal, entry_price, lot_size, quantity, target_price,
                                                              stoploss_price, option_data['rsi'],order_id, average_entry_price,actual_entry_date )
                            self.record_trade(signal, entry_price, None, 0, quantity, "Open", stoploss_price, None,average_entry_price, None,actual_entry_date)
                            active_trade = self.trade_manager.get_active_trade(
                                self.index_data_management.index['instrument_token'])
                            if active_trade:
                                self.webSocketManager.subscribe([active_trade['signal']['instrument_token']])
                            try:
                                self.send_whatsapp_message(f"Buying Algo Trade Started,\nIndex: {index['tradingsymbol']},\nEntry Time: {actual_entry_date},\nStrike: {signal['symbol']},\nEntry Price: {entry_price},\nActual Entry Price: {average_entry_price},\nStoploss: {stoploss_price},\nTarget: {target_price}")
                            except Exception as whatsappException:
                                self.send_whatsapp_message(f"Buying Algo Trade Started,\nA Trade was Bought but Whatsapp Message failed due to argument error.")

                            logger.info(f"Bought trade... Signal Entry Price: {entry_price},  Actual Average Entry Price: {average_entry_price}, Actual Entry Date: {actual_entry_date} Quantity: {quantity}, Target Price: {target_price}, Stoploss Price: {stoploss_price}")
                            logger.info(f"Placing stoploss order tradingsymbol : {signal['instrument']['tradingsymbol']} quantity : {quantity} stoploss_price : {stoploss_price}")

                            sl_order_id = self.place_sl_order(signal['instrument']['tradingsymbol'], quantity, stoploss_price)
                            if sl_order_id:
                                logger.info(f"Placed stoploss order for {sl_order_id}")
                                self.trade_manager.update_sl_order(self.index_data_management.index['instrument_token'], sl_order_id)
                            else:
                                logger.info(f"Not been able to place stoploss order. So retrying 5 times")
                                for _ in range(5):
                                    logger.info(f"Attempt {_} : Placing stoploss order tradingsymbol : {signal['instrument']['tradingsymbol']} quantity : {quantity} stoploss_price : {stoploss_price}")
                                    sl_order_id = self.place_sl_order(signal['instrument']['tradingsymbol'], quantity, stoploss_price)
                                    if sl_order_id:
                                        logger.info(f"Attempt {_} : Placed stoploss order {sl_order_id}")
                                        self.trade_manager.update_sl_order(self.index_data_management.index['instrument_token'], sl_order_id)
                                        break
                                    else:
                                        logger.info(f"Attempt {_} : Not able to place stoploss order")
                                else:
                                    logger.info(f"5 Attempts exhausted : Not able to place stoploss order, so getting active trade information to place sell order at market price")
                                    active_trade = self.trade_manager.get_active_trade(self.index_data_management.index['instrument_token'])
                                    if active_trade:
                                        logging.info(f"Active trade found. Placing sell order on market price for tradingsymbol : {active_trade['signal']['instrument']['tradingsymbol']} quantity : {active_trade['quantity']}")
                                        for _ in range(5):
                                            logger.info(f"Attempt {_} : Placing sell order tradingsymbol : {active_trade['signal']['instrument']['tradingsymbol']} quantity : {active_trade['quantity']}")
                                            sell_order_id = self.place_order(
                                                variety="regular",
                                                tradingsymbol=active_trade['signal']['instrument']['tradingsymbol'],
                                                exchange="NFO",
                                                transaction_type="SELL",
                                                order_type="MARKET",
                                                quantity=active_trade['quantity'],
                                                product="MIS",
                                                validity="DAY"
                                            )
                                            if sell_order_id:
                                                logger.info(f"Attempt {_} : Sell order placed with order id {sell_order_id}")
                                                while True:
                                                    logger.info(f"Attempt {_} : Checking the status of sell order id {sell_order_id}")
                                                    orderHistory = self.check_order(sell_order_id)
                                                    logger.info(f"Attempt {_} : Checked the status of sell order id {sell_order_id} with status as {orderHistory['status']}")
                                                    status = orderHistory['status']
                                                    if status == "COMPLETE":
                                                        logger.info(f"Attempt {_} : Checked the status of completed sell order id {sell_order_id} with status as {orderHistory['status']}")
                                                        average_exit_price = orderHistory['average_price']
                                                        logger.info(f"Exited at market price as sl limit order failed")
                                                        result = "Stopped out"
                                                        ist = pytz.timezone('Asia/Kolkata')
                                                        exit_datetime_obj = datetime.strptime(orderHistory['exchange_update_timestamp'],"%Y-%m-%d %H:%M:%S")
                                                        exit_datetime_obj_ist = ist.localize(exit_datetime_obj)
                                                        exit_date = exit_datetime_obj_ist
                                                        average_entry_price=active_trade['average_entry_price']
                                                        quantity = active_trade['quantity']
                                                        profit_loss = (average_exit_price - average_entry_price) * quantity
                                                        self.trade_manager.update_trade_status(trade_type='SELL', result=result, trade_time=exit_date,profit_loss=profit_loss,instrument_token=self.index_data_management.index[
                                                                           'instrument_token'],average_exit_price= average_exit_price)
                                                        self.record_trade(active_trade['signal'], active_trade['entry_price'], None, profit_loss, quantity, result, active_trade['stoploss_price'], exit_date,average_entry_price,average_exit_price)
                                                        logger.info(f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                                                        self.webSocketManager.unsubscribe([active_trade['signal']['instrument_token']])
                                                        try:
                                                            self.send_whatsapp_message(f"Trade Exited...\nBuying Algo,\nResult: {result},\nStrike: {active_trade['signal']['symbol']},\nIndex: {index['tradingsymbol']},\nEntry Time: {active_trade['actual_entry_date']},\nExit Time: {exit_date},\nEntry Price: {active_trade['entry_price']},\nActual Entry Price: {active_trade['average_entry_price']},\nActual Exit Price: {average_exit_price},\nP&L = {profit_loss}")
                                                        except Exception as whatsappException:
                                                            self.send_whatsapp_message(f"Buying Algo,\nA Trade was Completed but Whatsapp Message failed due to argument error.")
                                                        break
                                                    elif status in self.failureTerminatedOrderStatus:
                                                        logger.info(f"Attempt {_} : Checked the status of failed sell order id {sell_order_id} with status as {orderHistory['status']}")
                                                        logger.info(f"Attempt {_} : Sell Order also failed after SL order failure, so calling, emailing Dagar and raising alarm siren")
                                                        average_exit_price = ltp
                                                        result = "Stopped out"
                                                        exit_date = datetime.now()
                                                        average_entry_price = active_trade['average_entry_price']
                                                        quantity = active_trade['quantity']
                                                        exit_price = active_trade['stoploss_price']
                                                        profit_loss = (
                                                                                  average_exit_price - average_entry_price) * quantity
                                                        self.trade_manager.update_trade_status(trade_type='SELL',
                                                                                               result=result,
                                                                                               trade_time=exit_date,
                                                                                               profit_loss=profit_loss,
                                                                                               instrument_token=
                                                                                               self.index_data_management.index[
                                                                                                   'instrument_token'],
                                                                                               average_exit_price=average_exit_price)
                                                        self.record_trade(active_trade['signal'],
                                                                          active_trade['entry_price'], exit_price,
                                                                          profit_loss, quantity, result,
                                                                          active_trade['stoploss_price'], exit_date,
                                                                          average_entry_price, average_exit_price)
                                                        logger.info(
                                                            f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                                                        self.webSocketManager.unsubscribe(
                                                            [active_trade['signal']['instrument_token']])
                                                        self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure,\nIndex: {index['tradingsymbol']},\nStrike: {signal['symbol']}")
                                                        try:
                                                            self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure,\nIndex: {index['tradingsymbol']},\nStrike: {signal['symbol']}")
                                                        except Exception as whatsappException:
                                                            self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure. Whatsapp Message also failed due to argument error.")

                                                        # play_help_siren_threaded()
                                                        break
                                                    else:
                                                        logger.info(f"Attempt {_} : Checked the status of sell order id {sell_order_id} with status as {orderHistory['status']}")
                                                logger.info(f"Reached to selling last step when SL failed.")
                                                break
                                            else:
                                                logger.info(f"Attempt {_} : Not been able to place sell order. so retrying")
                                        else:
                                            logger.info(f"Attempts exhausted : Not able to place sell order and SL also failed, so calling, emailing, whatsapp Dagar and raising alarm siren")
                                            average_exit_price = ltp
                                            result = "Stopped out"
                                            exit_date = datetime.now()
                                            average_entry_price = active_trade['average_entry_price']
                                            quantity = active_trade['quantity']
                                            exit_price = active_trade['stoploss_price']
                                            profit_loss = (average_exit_price - average_entry_price) * quantity
                                            self.trade_manager.update_trade_status(trade_type='SELL', result=result,
                                                                                   trade_time=exit_date,
                                                                                   profit_loss=profit_loss,
                                                                                   instrument_token=
                                                                                   self.index_data_management.index[
                                                                                       'instrument_token'],
                                                                                   average_exit_price=average_exit_price)
                                            self.record_trade(active_trade['signal'], active_trade['entry_price'],
                                                              exit_price,
                                                              profit_loss, quantity, result,
                                                              active_trade['stoploss_price'], exit_date,
                                                              average_entry_price, average_exit_price)
                                            logger.info(
                                                f"Sold trade... Entry Price: {active_trade['entry_price']},  Average Entry Price {average_entry_price}, Actual Exit Price: {average_exit_price} , Quantity: {active_trade['quantity']}, Target Price: {active_trade['target_price']}, Stoploss Price: {active_trade['stoploss_price']}")
                                            self.webSocketManager.unsubscribe(
                                                [active_trade['signal']['instrument_token']])
                                            try:
                                                self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure,\nIndex: {index['tradingsymbol']},\nStrike: {signal['symbol']}")
                                            except Exception as whatsappException:
                                                self.send_whatsapp_message(f"Buying Algo,\nURGENT IMMEDIATE ACTION REQUIRED,\nSell Order also failed after SL order failure. Whatsapp Message also failed due to argument error.")
                                            # play_help_siren_threaded()
                                    else:
                                        logger.info(f"No Active Trade found. It may have been exited manually by Dagar")

                            break
                        elif status in self.failureTerminatedOrderStatus:
                            logger.info(f"Buy order has failed with order id {order_id} and status as {orderHistory['status']}")
                            break
                        else:
                            logger.info(f"Checked the status of order id {order_id} status {orderHistory['status']}")
                    logger.info(f"Reached to last step of buy order loop. Completed in {datetime.now() - start_time} time")
                    break
                else:
                    logger.info(f"Some error in placing buy order, so retrying")
            else:
                logger.info(f"ltp is 5% above the signal entry price, so retrying")
        logger.info("Active trade")
        logger.info(self.trade_manager.active_trades)
        logger.info("Closed trade")
        logger.info(self.trade_manager.closed_trades)

    def record_trade(self, signal, entry_price, exit_price, profit_loss, quantity, result, initial_stoploss_price, exit_date,average_entry_price,average_exit_price,actual_entry_date=None):
        new_trade = {
            "Date": signal['date'],
            "Type": signal['type'],
            "Entry Price": entry_price,
            "Actual Entry Price": average_entry_price,
            "Actual Exit Price": average_exit_price,
            "Exit Price": exit_price,
            "Profit/Loss": profit_loss,
            "Trade Quantity": quantity,
            "Option Symbol": signal['symbol'],
            "Result": result,
            "Index Name": self.config['INDEX_DETAILS'][self.config['current_index']]['tradingsymbol'],
            "Index LTP": signal.get('indexLtp', None),
            "Stoploss Begin": initial_stoploss_price,
            "Exit Date": exit_date
        }
        self.trades = pd.concat([self.trades, pd.DataFrame([new_trade])], ignore_index=True)
        logging.info(f"Recorded trade: {new_trade}")

    def summarize_performance(self):
        self.trades['Date'] = pd.to_datetime(self.trades['Date']).dt.date
        unique_trades = self.trades.drop_duplicates(subset=['Date', 'Type', 'Entry Price', 'Exit Price', 'Profit/Loss'])
        daily_performance = unique_trades.groupby('Date').agg(
            Total_Profit_Loss=('Profit/Loss', 'sum'),
            Number_of_Trades=('Date', 'size'),
            Average_Profit_Loss=('Profit/Loss', 'mean'),
            Max_Profit=('Profit/Loss', 'max'),
            Min_Loss=('Profit/Loss', 'min')
        )
        return daily_performance

    def generate_trade_report(self):
        if self.trades.empty:
            logger.info("No trades to report.")
            return

        # Ensure 'Date' and 'Exit Date' are in datetime format and handle any errors in conversion
        self.trades['Date'] = pd.to_datetime(self.trades['Date'], errors='coerce')
        self.trades['Exit Date'] = pd.to_datetime(self.trades['Exit Date'], errors='coerce')

        # Handle any rows where 'Date' or 'Exit Date' conversion failed
        if self.trades['Date'].isna().any() or self.trades['Exit Date'].isna().any():
            logger.info("Warning: Some dates couldn't be converted and will be excluded from the report.")
            self.trades.dropna(subset=['Date', 'Exit Date'], inplace=True)

        # Filter only executed trades
        executed_trades = self.trades[self.trades['Result'].isin(
            ['Stopped out', 'Target reached', 'Exited at 2:30 PM', 'Normal exit'])]

        # Remove duplicates if any
        executed_trades = executed_trades.drop_duplicates()

        # Create a report DataFrame from the filtered trades DataFrame
        report = executed_trades.copy()
        report['S.No'] = range(1, len(report) + 1)
        report['DateTime for Entry'] = report['Date'].dt.strftime('%Y-%m-%d %H:%M:%S')  # Format date and time
        report['Index Name'] = self.config['INDEX_DETAILS'][self.config['current_index']]['tradingsymbol']
        report['Index LTP'] = report['Index LTP']  # Ensure this column exists or is calculated beforehand
        report['Strike'] = report['Option Symbol']
        report['Quantity'] = report['Trade Quantity']
        report['Entry'] = report['Entry Price']
        report['Stoploss Begin'] = report['Stoploss Begin']  # Ensure this is recorded during trade execution
        report['Exit'] = report['Exit Price']
        report['Exit Time'] = report['Exit Date'].dt.strftime('%Y-%m-%d %H:%M:%S')  # Format date and time
        report['Profit/Loss'] = report['Profit/Loss']
        report['Capital Deployed'] = report['Entry Price'] * report['Trade Quantity']

        # Reordering columns to match the specified format
        report = report[['S.No', 'DateTime for Entry', 'Index Name', 'Index LTP', 'Strike', 'Quantity',
                         'Entry', 'Stoploss Begin', 'Exit', 'Exit Time', 'Profit/Loss', 'Capital Deployed']]

        # Printing the report
        pd.set_option('display.max_rows', None)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        pd.set_option('display.max_colwidth', None)
        logger.info(report)

        return report

    # def simulate_order(self, signal):
    #     """Simulate placing an order based on a trading signal."""
    #     logging.info(f"Simulating order for {signal['type']} at {signal['date']}")
    #     logger.info(f"Simulating order for {signal['type']} at {signal['date']}")
    #
    #     # Check if trading is allowed based on current rules in TradeManager
    #     current_time = pd.to_datetime(signal['date'])
    #     if not self.trade_manager.can_trade(current_time, signal['type'], signal['instrument_token']):
    #         logging.warning(f"Trade not allowed by TradeManager for {signal['type']} at {current_time}")
    #         logger.info(f"Trade not allowed by TradeManager for {signal['type']} at {current_time}")
    #         return None
    #
    #     option_data = self.odm.fetch_option_data(signal['instrument_token'])
    #     if option_data.empty:
    #         logging.error(f"No option data available for processing the signal on {signal['date']}")
    #         logger.info(f"No option data available for processing the signal on {signal['date']}")
    #         return None
    #
    #     sl_manager = SLManagement(option_data)
    #     entry_index = sl_manager.find_entry_index(current_time)
    #
    #     entry_price = option_data.loc[entry_index, 'close']
    #     lot_size = self.config['INDEX_DETAILS'][self.config['current_index']]['lot_size']
    #     quantity = self.config['TRADE_SIZE'] // (entry_price * lot_size) * lot_size
    #     target_price, stoploss_price = sl_manager.calculate_targets_stoploss(entry_index)
    #
    #     # Simulate trade execution
    #     self.record_trade(signal, entry_price, quantity, target_price, stoploss_price)
    #     self.trade_manager.register_trade(signal['type'], current_time, signal['instrument_token'], signal, entry_price, lot_size, quantity, target_price, stoploss_price)
    #     logger.info(f"Trade simulated and recorded: Entry Price: {entry_price}, Target Price: {target_price}, Stoploss Price: {stoploss_price}, Quantity: {quantity}")
    #
    #     return entry_price, target_price, stoploss_price, quantity

    # def record_trade(self, signal, entry_price, quantity, target_price, stoploss_price):
    #     new_trade = {
    #         "Date": signal['date'],
    #         "Type": signal['type'],
    #         "Entry Price": entry_price,
    #         "Quantity": quantity,
    #         "Target Price": target_price,
    #         "Stoploss Price": stoploss_price
    #     }
    #     self.trades = pd.concat([self.trades, pd.DataFrame([new_trade])], ignore_index=True)
    #     logging.info(f"Recorded trade: {new_trade}")
    #     logger.info(f"Recorded trade: {new_trade}")

    # def close_trade(self, instrument_token, exit_price, exit_date):
    #     # Logic to close the trade and calculate the profit or loss
    #     trade = self.trades[self.trades['Type'] == instrument_token].iloc[-1]
    #     trade['Exit Price'] = exit_price
    #     trade['Exit Date'] = exit_date
    #     trade['Profit/Loss'] = (exit_price - trade['Entry Price']) * trade['Quantity']
    #     logging.info(f"Trade closed for {instrument_token} with P/L: {trade['Profit/Loss']}")
    #     logger.info(f"Trade closed for {instrument_token} with P/L: {trade['Profit/Loss']}")
    #
    # def generate_trade_report(self):
    #     return self.trades

# Example usage:
# if __name__ == "__main__":
#     play_bought_siren_threaded()
#     play_help_siren_threaded()
#     print("Main program continues to run...")
#     logger.info("Both siren")

