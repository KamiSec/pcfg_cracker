#!/usr/bin/env python3

import sys
import os 


#########################################################################################################
# Contains an index into the Markov grammar
# Used to generate the "next" guess
# Just holds variables, no real fuctions
#########################################################################################################
class MarkovIndex:
    
    ############################################################################################
    # Create a new guess generation session with a minimum and maximum rank thresholds
    # This should occur before creating guesses
    ############################################################################################
    def __init__(self, min_level = 0, max_level = 1000):
        self.min_level = min_level
        self.max_level = max_level
        self.guess = None
        self.guess_level = 0

#########################################################################################################
# Contains all the logic for handling Markov guess generation for the pcfg_manager
# Based on --markov mode in John the Ripper
# Seperating this out since I expect to do more work later on refining how brute force generation is
# used in the grammar
#########################################################################################################
class MarkovCracker:

    ############################################################################################
    # Initializes the cracker
    # If rule directory is none, then the cracker will basically act as a noop
    ############################################################################################
    def __init__(self, rule_directory = None):
        self.markov_stats = {}
        self.start_letter = None
        
        if rule_directory != None:
            if not self.load_markov_stats(rule_directory):
                raise
        
        ##Used for guess generation
        self.min_level = None
        self.max_level = None
        self.guess = None
        self.guess_level = 0
        
        
    #####################################################################################
    # Loads the Markov Stats from a file
    # The stats file is a dictionary lookup for zero order and first order Markov items
    # Creating a form similar to OrderedDictionary so we can have a "next" function to
    # generate the next guess after the previous one in a repetable way
    # Takes the form of
    #   'a':{
    #       'probability':5,
    #       'next': 'b',
    #       'first_child':'a',
    #       'last_child':'b',    
    #       'following_letters':{
    #           'a':{'probability':10, 'next':'b'},
    #           'b':{'probability':10, 'next':None},
    #       }
    ######################################################################################
    def load_markov_stats(self, rule_directory):
        print("Loading the Markov stats file",file=sys.stderr)

        filename = os.path.join(rule_directory, 'Markov', 'markov_stats.txt')
        
        try:
            # The stats file is in the format JtR uses for their Markov mode
            # Note, since this training program supports non-ascii characters this can produce stats files
            # not suited for JtR since it assumes a maximum of 256 characters
            #
            # Format:
            #    Probability=proba1[ORD_REP1]
            #    Probability=proba2[ORD_REP1*256+ORD_REP2]
            #
            # Example:
            #    27=proba1[97]                  //'a' has probability 27
            #    85=proba2[97*256+114]          //'r' given 'a' has a probability of 85
            #    83=proba2[97*256+100]          //'d' given 'a' has a probability of 83
            with open(filename, 'r') as file:
                prev_proba1 = None
                for line in file:
                    ##--Handle the 0 order Markov
                    if '=proba1' in line:
                        ##--Yes this parsing is a bit hackish. It would be easy if I saved
                        ##--the data in a different format but I want to maintian compatability with
                        ##--JtR's stat file format
                        results = line.strip().split("=proba1[")
                        results[1] = results[1][:-1]
                        letter = chr(int(results[1]))
                        prob = int(results[0])
                        
                        ##--Save the result in the dictionary
                        self.markov_stats[letter] = {'probability':prob, 'following_letters':{}, 'first_child':None, 'last_child':None, 'next':None}
                        
                        ##--Update the OrderedDictionary like links
                        if self.start_letter == None:
                            self.start_letter = letter
                        
                        if prev_proba1 != None:
                            self.markov_stats[prev_proba1]['next'] = letter
                        prev_proba1 = letter
                                               
                    elif '=proba2' in line:
                        results = line.strip().split("=proba2[")
                        prob = int(results[0])
                        results = results[1].split('*256+')
                        letter1 = chr(int(results[0]))
                        letter2 = chr(int(results[1][:-1]))
                        self.markov_stats[letter1]['following_letters'][letter2] = {'probability':prob, 'next':None}
                        
                        ##--Update the OrderedDictionary like links
                        #-Do the 1st order Markov links
                        if self.markov_stats[letter1]['last_child'] != None:
                            self.markov_stats[letter1]['following_letters'][self.markov_stats[letter1]['last_child']]['next'] = letter2
                        
                        #-Do the 0 order Markov links
                        if self.markov_stats[letter1]['first_child'] == None:
                            self.markov_stats[letter1]['first_child'] = letter2
                        self.markov_stats[letter1]['last_child'] = letter2
                                                             
                    else:
                        print('Invalid line in Markov stats file')
                        print(line)
                        return None

        except Exception as msg:
            print (msg,file=sys.stderr)
            print ("Error opening file " + filename, file=sys.stderr)
            return None

        return True
         
     
    ###############################################################################################
    # Generates the "next" guess from this model
    # Will return None when no more guesses are left to be created
    ###############################################################################################
    def next_guess(self, markov_index):
        
        ##--Deal with starting off the Markov chain
        if markov_index.guess == None:
            markov_index.guess = [self.start_letter]
            markov_index.guess_level = self.markov_stats[self.start_letter]['probability']
            
            if markov_index.guess_level >= markov_index.min_level and markov_index.guess_level <= markov_index.max_level:
                return ''.join(markov_index.guess)          
        
        while True:

            ##--Loop through the following letter probabilities first
            ret_value = self.dig_deeper(markov_index)
            if ret_value != None:
                return ret_value

            ##--Now back out and try other letters at the same depth, or lower
            while True:
                parent_letter = markov_index.guess[-1]
                
                ##--If it is the first letter in the chain
                if len(markov_index.guess) == 1:
                    more_work, ret_value = self.dig_wider_base(markov_index, parent_letter)
                    if more_work != True:
                        return ret_value
                    else:
                        break
                
                ##--If we are looking at the 1st Markov Order probabilities
                else:
                    prev_letter = markov_index.guess[-2]
                    ##--Update the guess level to account for the missing children
                    markov_index.guess_level = markov_index.guess_level - self.markov_stats[prev_letter]['following_letters'][parent_letter]['probability']
                    
                    cur_letter = self.markov_stats[prev_letter]['following_letters'][parent_letter]['next']
                    
                    ##--No more children at this level, go back up a level
                    if cur_letter == None:
                        del markov_index.guess[-1] 
                        continue

                    ##--Update the probability with the new item
                    cur_level = markov_index.guess_level + self.markov_stats[prev_letter]['following_letters'][cur_letter]['probability']         
                    
                    ##--This is a valid guess--##
                    if cur_level >= markov_index.min_level and cur_level <= markov_index.max_level:
                        markov_index.guess_level = cur_level
                        markov_index.guess[-1] = cur_letter
                        return ''.join(markov_index.guess)
                        
                    ##--Must dig deeper              
                    elif cur_level < markov_index.max_level:
                        markov_index.guess_level = cur_level
                        markov_index.guess[-1] = cur_letter
                        break
            
                    ##--No more children at this level since all of their levels are too high
                    del markov_index.guess[-1]
            
        return None
    
    #########################################################################
    # Dig wider for the first character. Aka go from 'a' to 'b' to 'c'
    #########################################################################
    def dig_wider_base(self, markov_index, parent_letter):
        cur_letter = self.markov_stats[parent_letter]['next']
                    
        ##--If we are done with all of the letters
        if cur_letter == None:
            markov_index.guess = None
            return False, None
            
        markov_index.guess_level = self.markov_stats[cur_letter]['probability']
        
        ##--If we don't need to continue on since the level of following letters is too high
        if markov_index.guess_level > markov_index.max_level:
            markov_index.guess = None
            return False, None
        
        ##--It potentially is a valid guess
        markov_index.guess[-1] = cur_letter
        
        ##--Check to see if this is a valid guess
        if markov_index.guess_level >= markov_index.min_level and markov_index.guess_level <= markov_index.max_level:
            return False, ''.join(markov_index.guess)
        
        ##--Must dig deeper              
        return True, None
            
    
    #########################################################################
    # Go down the markov chain. Aka go from 'a' to 'aa' to 'aaa'
    #########################################################################
    def dig_deeper(self, markov_index):
        while True:
            prev_letter = markov_index.guess[-1]
            cur_letter = self.markov_stats[prev_letter]['first_child']
            if cur_letter == None:
                return None
            
            cur_level = markov_index.guess_level + self.markov_stats[prev_letter]['following_letters'][cur_letter]['probability']
            
            if cur_level >= markov_index.min_level and cur_level <= markov_index.max_level:
                markov_index.guess.append(cur_letter)
                markov_index.guess_level = cur_level
                return ''.join(markov_index.guess)
            
            ##--We dug too deep, went too far, unleashed the eldritch horrors                
            elif cur_level > markov_index.max_level:
                return None
            
            ##--Add the letter on and keep digging
            markov_index.guess.append(cur_letter)
            markov_index.guess_level = cur_level
            