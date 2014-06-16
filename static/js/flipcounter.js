/**
 * Apple-Style Flip Counter
 * Version 0.5.3 - May 7, 2011
 *
 * Copyright (c) 2010 Chris Nanney
 * http://cnanney.com/journal/code/apple-style-counter-revisited/
 *
 * Licensed under MIT
 * http://www.opensource.org/licenses/mit-license.php
 */

var flipCounter = function(d, options){

	// Default values
	var defaults = {
		value: 0,
		inc: 1,
		pace: 1000,
		auto: true,
		tFH: 20,		// Top Height: default 39
		bFH: 40,		// Bottom Height: default 64
		fW: 29,			// Width: default 53
		bOffset: 200	// default 390
	};

	var	doc = window.document,
	divId = typeof d !== 'undefined' && d !== '' ? d : 'flip-counter',
	div = doc.getElementById(divId);

    var o = {};
    for (var opt in defaults) {
        o[opt] = (opt in options) ? options[opt] : defaults[opt];
    }

	var digitsOld = [], digitsNew = [], subStart, subEnd, x, y, nextCount = null, newDigit, newComma,
	best = {
		q: null,
		pace: 0,
		inc: 0
	};

	/**
	 * Sets the value of the counter and animates the digits to new value.
	 *
	 * Example: myCounter.setValue(500); would set the value of the counter to 500,
	 * no matter what value it was previously.
	 *
	 * @param {int} n
	 *   New counter value
	 */
	this.setValue = function(n){
		if (isNumber(n)){
			x = o.value;
			y = n;
			o.value = n;
			digitCheck(x,y);
		}
		return this;
	};

	/**
	 * Sets the increment for the counter. Does NOT animate digits.
	 */
	this.setIncrement = function(n){
		o.inc = isNumber(n) ? n : defaults.inc;
		return this;
	};

	/**
	 * Sets the pace of the counter. Only affects counter when auto == true.
	 *
	 * @param {int} n
	 *   New pace for counter in milliseconds
	 */
	this.setPace = function(n){
		o.pace = isNumber(n) ? n : defaults.pace;
		return this;
	};

	/**
	 * Sets counter to auto-incrememnt (true) or not (false).
	 *
	 * @param {bool} a
	 *   Should counter auto-increment, true or false
	 */
	this.setAuto = function(a){
		if (a && ! o.auto){
			o.auto = true;
			doCount();
		}
		if (! a && o.auto){
			if (nextCount) clearNext();
			o.auto = false;
		}
		return this;
	};

	/**
	 * Increments counter by one animation based on set 'inc' value.
	 */
	this.step = function(){
		if (! o.auto) doCount();
		return this;
	};

	/**
	 * Adds a number to the counter value, not affecting the 'inc' or 'pace' of the counter.
	 *
	 * @param {int} n
	 *   Number to add to counter value
	 */
	this.add = function(n){
		if (isNumber(n)){
			x = o.value;
			o.value += n;
			y = o.value;
			digitCheck(x,y);
		}
		return this;
	};

	/**
	 * Subtracts a number from the counter value, not affecting the 'inc' or 'pace' of the counter.
	 *
	 * @param {int} n
	 *   Number to subtract from counter value
	 */
	this.subtract = function(n){
		if (isNumber(n)){
			x = o.value;
			o.value -= n;
			if (o.value >= 0){
				y = o.value;
			}
			else{
				y = "0";
				o.value = 0;
			}
			digitCheck(x,y);
		}
		return this;
	};

	/**
	 * Increments counter to given value, animating by current pace and increment.
	 *
	 * @param {int} n
	 *   Number to increment to
	 * @param {int} t (optional)
	 *   Time duration in seconds - makes increment a 'smart' increment
	 * @param {int} p (optional)
	 *   Desired pace for counter if 'smart' increment
	 */
	this.incrementTo = function(n, t, p){
		if (nextCount) clearNext();

		// Smart increment
		if (typeof t != 'undefined'){
			var time = isNumber(t) ? t * 1000 : 10000,
			pace = typeof p != 'undefined' && isNumber(p) ? p : o.pace,
			diff = typeof n != 'undefined' && isNumber(n) ? n - o.value : 0,
			cycles, inc, check, i = 0;
			best.q = null;

			// Initial best guess
			pace = (time / diff > pace) ? Math.round((time / diff) / 10) * 10 : pace;
			cycles = Math.floor(time / pace);
			inc = Math.floor(diff / cycles);

			check = checkSmartValues(diff, cycles, inc, pace, time);

			if (diff > 0){
				while (check.result === false && i < 100){
					pace += 10;
					cycles = Math.floor(time / pace);
					inc = Math.floor(diff / cycles);

					check = checkSmartValues(diff, cycles, inc, pace, time);
					i++;
				}

				if (i == 100){
					// Could not find optimal settings, use best found so far
					o.inc = best.inc;
					o.pace = best.pace;
				}
				else{
					// Optimal settings found, use those
					o.inc = inc;
					o.pace = pace;
				}

				doIncrement(n, true, cycles);
			}

		}
		// Regular increment
		else{
			doIncrement(n);
		}

	}

	/**
	 * Gets current value of counter.
	 */
	this.getValue = function(){
		return o.value;
	}

	/**
	 * Stops all running increments.
	 */
	this.stop = function(){
		if (nextCount) clearNext();
		return this;
	}

	//---------------------------------------------------------------------------//

	function doCount(){
		x = o.value;
		o.value += o.inc;
		y = o.value;
		digitCheck(x,y);
		if (o.auto === true) nextCount = setTimeout(doCount, o.pace);
	}

	function doIncrement(n, s, c){
		var val = o.value,
		smart = (typeof s == 'undefined') ? false : s,
		cycles = (typeof c == 'undefined') ? 1 : c;

		if (smart === true) cycles--;

		if (val != n){
			x = o.value,
			o.auto = true;

			if (val + o.inc <= n && cycles != 0) val += o.inc
			else val = n;

			o.value = val;
			y = o.value;

			digitCheck(x,y);
			nextCount = setTimeout(function(){doIncrement(n, smart, cycles)}, o.pace);
		}
		else o.auto = false;
	}

	function digitCheck(x,y){
		digitsOld = splitToArray(x);
		digitsNew = splitToArray(y);
		var diff,
		xlen = digitsOld.length,
		ylen = digitsNew.length;
		if (ylen > xlen){
			diff = ylen - xlen;
			while (diff > 0){
				addDigit(ylen - diff + 1, digitsNew[ylen - diff]);
				diff--;
			}
		}
		if (ylen < xlen){
			diff = xlen - ylen;
			while (diff > 0){
				removeDigit(xlen - diff);
				diff--;
			}
		}
		for (var i = 0; i < xlen; i++){
			if (digitsNew[i] != digitsOld[i]){
				animateDigit(i, digitsOld[i], digitsNew[i]);
			}
		}
	}

	function animateDigit(n, oldDigit, newDigit){
		var speed, step = 0, w, a,
		bp = [
			'-' + o.fW + 'px -' + (oldDigit * o.tFH) + 'px',
			(o.fW * -2) + 'px -' + (oldDigit * o.tFH) + 'px',
			'0 -' + (newDigit * o.tFH) + 'px',
			'-' + o.fW + 'px -' + (oldDigit * o.bFH + o.bOffset) + 'px',
			(o.fW * -2) + 'px -' + (newDigit * o.bFH + o.bOffset) + 'px',
			(o.fW * -3) + 'px -' + (newDigit * o.bFH + o.bOffset) + 'px',
			'0 -' + (newDigit * o.bFH + o.bOffset) + 'px'
		];

		if (o.auto === true && o.pace <= 300){
			switch (n){
				case 0:
					speed = o.pace/6;
					break;
				case 1:
					speed = o.pace/5;
					break;
				case 2:
					speed = o.pace/4;
					break;
				case 3:
					speed = o.pace/3;
					break;
				default:
					speed = o.pace/1.5;
					break;
			}
		}
		else{
			speed = 80;
		}
		// Cap on slowest animation can go
		speed = (speed > 80) ? 80 : speed;

		function animate(){
			if (step < 7){
				w = step < 3 ? 't' : 'b';
				a = doc.getElementById(divId + "_" + w + "_d" + n);
				if (a) a.style.backgroundPosition = bp[step];
				step++;
				if (step != 3) setTimeout(animate, speed);
				else animate();
			}
		}

		animate();
	}

	// Creates array of digits for easier manipulation
	function splitToArray(input){
		return input.toString().split("").reverse();
	}

	// Adds new digit
	function addDigit(len, digit){
		var li = Number(len) - 1;
		newDigit = doc.createElement("ul");
		newDigit.className = 'cd';
		newDigit.id = divId + '_d' + li;
		newDigit.innerHTML = '<li class="t" id="' + divId + '_t_d' + li + '"></li><li class="b" id="' + divId + '_b_d' + li + '"></li>';

		if (li % 3 == 0){
			newComma = doc.createElement("ul");
			newComma.className = 'cd';
			newComma.innerHTML = '<li class="s"></li>';
			div.insertBefore(newComma, div.firstChild);
		}

		div.insertBefore(newDigit, div.firstChild);
		doc.getElementById(divId + "_t_d" + li).style.backgroundPosition = '0 -' + (digit * o.tFH) + 'px';
		doc.getElementById(divId + "_b_d" + li).style.backgroundPosition = '0 -' + (digit * o.bFH + o.bOffset) + 'px';
	}

	// Removes digit
	function removeDigit(id){
		var remove = doc.getElementById(divId + "_d" + id);
		div.removeChild(remove);

		// Check for leading comma
		var first = div.firstChild.firstChild;
		if ((" " + first.className + " ").indexOf(" s ") > -1 ){
			remove = first.parentNode;
			div.removeChild(remove);
		}
	}

	// Sets the correct digits on load
	function initialDigitCheck(init){
		// Creates the right number of digits
		var initial = init.toString(),
		count = initial.length,
		bit = 1, i;
		for (i = 0; i < count; i++){
			newDigit = doc.createElement("ul");
			newDigit.className = 'cd';
			newDigit.id = divId + '_d' + i;
			newDigit.innerHTML = newDigit.innerHTML = '<li class="t" id="' + divId + '_t_d' + i + '"></li><li class="b" id="' + divId + '_b_d' + i + '"></li>';
			div.insertBefore(newDigit, div.firstChild);
			if (bit != (count) && bit % 3 == 0){
				newComma = doc.createElement("ul");
				newComma.className = 'cd';
				newComma.innerHTML = '<li class="s"></li>';
				div.insertBefore(newComma, div.firstChild);
			}
			bit++;
		}
		// Sets them to the right number
		var digits = splitToArray(initial);
		for (i = 0; i < count; i++){
			doc.getElementById(divId + "_t_d" + i).style.backgroundPosition = '0 -' + (digits[i] * o.tFH) + 'px';
			doc.getElementById(divId + "_b_d" + i).style.backgroundPosition = '0 -' + (digits[i] * o.bFH + o.bOffset) + 'px';
		}
		// Do first animation
		if (o.auto === true) nextCount = setTimeout(doCount, o.pace);
	}

	// Checks values for smart increment and creates debug text
	function checkSmartValues(diff, cycles, inc, pace, time){
		var r = {result: true}, q;
		// Test conditions, all must pass to continue:
		// 1: Unrounded inc value needs to be at least 1
		r.cond1 = (diff / cycles >= 1) ? true : false;
		// 2: Don't want to overshoot the target number
		r.cond2 = (cycles * inc <= diff) ? true : false;
		// 3: Want to be within 10 of the target number
		r.cond3 = (Math.abs(cycles * inc - diff) <= 10) ? true : false;
		// 4: Total time should be within 100ms of target time.
		r.cond4 = (Math.abs(cycles * pace - time) <= 100) ? true : false;
		// 5: Calculated time should not be over target time
		r.cond5 = (cycles * pace <= time) ? true : false;

		// Keep track of 'good enough' values in case can't find best one within 100 loops
		if (r.cond1 && r.cond2 && r.cond4 && r.cond5){
			q = Math.abs(diff - (cycles * inc)) + Math.abs(cycles * pace - time);
			if (best.q === null) best.q = q;
			if (q <= best.q){
				best.pace = pace;
				best.inc = inc;
			}
		}

		for (var i = 1; i <= 5; i++){
			if (r['cond' + i] === false){
				r.result = false;
			}
		}
		return r;
	}

	// http://stackoverflow.com/questions/18082/validate-numbers-in-javascript-isnumeric/1830844
	function isNumber(n) {
		return !isNaN(parseFloat(n)) && isFinite(n);
	}

	function clearNext(){
		clearTimeout(nextCount);
		nextCount = null;
	}

	// Start it up
	initialDigitCheck(o.value);
};
